"""Neural sequence models. ``torch`` is imported here and only here.

Two architectures, both predicting P(correct at t | events < t):

* ``DKT`` — Deep Knowledge Tracing (Piech et al. 2015): a GRU over one-hot
  (concept, correct) interactions. The reference deep baseline.

* ``Aquilante`` — the candidate. A causal self-attention encoder over
  interaction embeddings, in the spirit of SAKT (Pandey & Karypis 2019),
  with what the baselines cannot use: the **time gap** since the previous
  event and since the previous event on the same concept (log-days, as
  learned monotone features), the learner's stated confidence when present,
  hints and response time, and an explicit **forgetting gate** — a per-
  concept decay applied to the attended memory as a function of the concept
  gap. The query at step ``t`` is the concept about to be answered; keys and
  values are the interactions before ``t``. Ablation flags switch each
  ingredient off so the benchmark can say which ones earn their place.

Uncertainty: both models support MC dropout at inference (``predict`` with
``samples > 1`` returns mean and standard deviation across stochastic
passes). A temperature learned on the validation set (``calibrate``)
corrects the mean's calibration. These are the two cheapest methods that
work; ensembles are available by training several seeds and averaging in
``benchmarks``.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

from aquilante.features.sequences import Dataset, Sequence

try:  # torch is optional for the package, required for this module
    import torch
    from torch import nn
    from torch.nn import functional as F  # noqa: N812
except ImportError as exc:  # pragma: no cover
    raise ImportError("aquilante.models.neural needs PyTorch: pip install 'aquilante[torch]'") from exc


# ── batching ─────────────────────────────────────────────────────────────


def _pad(arrs: list[np.ndarray], max_len: int, dtype, fill=0) -> torch.Tensor:
    out = np.full((len(arrs), max_len), fill, dtype=dtype)
    for i, a in enumerate(arrs):
        a = a[-max_len:]
        out[i, : len(a)] = a
    return torch.from_numpy(out)


@dataclass
class Batch:
    concept: torch.Tensor  # [B, T] long
    item: torch.Tensor  # [B, T] long
    correct: torch.Tensor  # [B, T] float (targets)
    prev_correct: torch.Tensor  # [B, T] long: 0 pad, 1 wrong, 2 right, for the *previous* step
    gap: torch.Tensor  # [B, T] float log-days since previous event
    gap_concept: torch.Tensor  # [B, T] float log-days since previous event on this concept
    response: torch.Tensor  # [B, T] float log-ms of the *previous* event
    hints: torch.Tensor  # [B, T] long hints on the *previous* event (0..3)
    response_now: (
        torch.Tensor
    )  # [B, T] float log-ms of the event at t (memory feature; never a query feature)
    hints_now: torch.Tensor  # [B, T] long hints on the event at t
    prior_seen: torch.Tensor  # [B, T] float log1p prior exposures of this concept
    mask: torch.Tensor  # [B, T] bool: real positions

    def to(self, device) -> Batch:
        return Batch(**{k: v.to(device) for k, v in self.__dict__.items()})


def make_batch(seqs: list[Sequence], max_len: int) -> Batch:
    T = min(max_len, max(len(s) for s in seqs))

    def shifted(a: np.ndarray, fill):
        return np.concatenate([[fill], a[:-1]])

    return Batch(
        concept=_pad([s.concept for s in seqs], T, np.int64),
        item=_pad([s.item for s in seqs], T, np.int64),
        correct=_pad([s.correct.astype(np.float32) for s in seqs], T, np.float32),
        prev_correct=_pad([shifted(s.correct.astype(np.int64) + 1, 0) for s in seqs], T, np.int64),
        gap=_pad([s.log_gap for s in seqs], T, np.float32),
        gap_concept=_pad([s.log_gap_concept for s in seqs], T, np.float32),
        response=_pad([shifted(s.response_log_ms, 0.0) for s in seqs], T, np.float32),
        hints=_pad([shifted(s.hints.astype(np.int64), 0) for s in seqs], T, np.int64),
        response_now=_pad([s.response_log_ms for s in seqs], T, np.float32),
        hints_now=_pad([s.hints.astype(np.int64) for s in seqs], T, np.int64),
        prior_seen=_pad([np.log1p(s.prior_seen.astype(np.float32)) for s in seqs], T, np.float32),
        mask=_pad([np.ones(len(s), dtype=bool) for s in seqs], T, bool, False),
    )


# ── configs ──────────────────────────────────────────────────────────────


@dataclass
class DKTConfig:
    hidden: int = 64
    dropout: float = 0.2
    max_len: int = 200


@dataclass
class AquilanteConfig:
    d_model: int = 64
    heads: int = 4
    layers: int = 1
    dropout: float = 0.2
    max_len: int = 200
    # ablations
    use_time: bool = True
    use_forgetting: bool = True
    use_response: bool = True
    use_hints: bool = True
    use_item: bool = True


# ── DKT ──────────────────────────────────────────────────────────────────


class DKT(nn.Module):
    name = "dkt"

    def __init__(self, n_concepts: int, cfg: DKTConfig):
        super().__init__()
        self.cfg = cfg
        self.n_concepts = n_concepts
        # interaction = concept × {wrong, right}; index 0 = start token
        self.inter = nn.Embedding(2 * n_concepts + 1, cfg.hidden, padding_idx=0)
        self.gru = nn.GRU(cfg.hidden, cfg.hidden, batch_first=True)
        self.drop = nn.Dropout(cfg.dropout)
        self.out = nn.Linear(cfg.hidden, n_concepts)

    def forward(self, b: Batch) -> torch.Tensor:
        # previous interaction as input; predict current concept's correctness
        prev_concept = torch.cat([torch.zeros_like(b.concept[:, :1]), b.concept[:, :-1]], dim=1)
        prev = torch.where(
            b.prev_correct > 0,
            prev_concept + (b.prev_correct - 1) * self.n_concepts,
            torch.zeros_like(prev_concept),
        )
        h, _ = self.gru(self.drop(self.inter(prev)))
        logits = self.out(self.drop(h))  # [B, T, C]
        return logits.gather(-1, b.concept.unsqueeze(-1)).squeeze(-1)


# ── Aquilante ────────────────────────────────────────────────────────────


class Aquilante(nn.Module):
    name = "aquilante"

    def __init__(self, n_concepts: int, n_items: int, cfg: AquilanteConfig):
        super().__init__()
        self.cfg = cfg
        d = cfg.d_model
        self.concept = nn.Embedding(n_concepts, d, padding_idx=0)
        self.item = nn.Embedding(n_items, d, padding_idx=0) if cfg.use_item else None
        self.outcome = nn.Embedding(3, d, padding_idx=0)  # prev: pad/wrong/right
        self.hints = nn.Embedding(4, d, padding_idx=0) if cfg.use_hints else None
        # continuous features → d, each through a small monotone-friendly MLP
        self.time = nn.Sequential(nn.Linear(2, d), nn.GELU(), nn.Linear(d, d)) if cfg.use_time else None
        self.response = (
            nn.Sequential(nn.Linear(1, d), nn.GELU(), nn.Linear(d, d)) if cfg.use_response else None
        )
        self.exposure = nn.Linear(1, d)
        self.pos = nn.Embedding(cfg.max_len, d)
        layer = nn.TransformerEncoderLayer(
            d_model=d,
            nhead=cfg.heads,
            dim_feedforward=2 * d,
            dropout=cfg.dropout,
            batch_first=True,
            norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=cfg.layers)
        self.query_norm = nn.LayerNorm(d)
        self.attn = nn.MultiheadAttention(d, cfg.heads, dropout=cfg.dropout, batch_first=True)
        # forgetting gate: per-concept decay rate over log-gap on the same concept
        self.forget_rate = nn.Embedding(n_concepts, 1) if cfg.use_forgetting else None
        if self.forget_rate is not None:
            nn.init.constant_(self.forget_rate.weight, -1.0)
        self.start = nn.Parameter(torch.zeros(1, 1, d))
        self.head = nn.Sequential(
            nn.LayerNorm(2 * d),
            nn.Linear(2 * d, d),
            nn.GELU(),
            nn.Dropout(cfg.dropout),
            nn.Linear(d, 1),
        )
        self.drop = nn.Dropout(cfg.dropout)

    def _interaction(self, b: Batch) -> torch.Tensor:
        """Embedding of the interaction at each position: concept, outcome, item, response, hints."""
        outcome = ((b.correct > 0.5).long() + 1) * b.mask.long()
        x = self.concept(b.concept) + self.outcome(outcome)
        if self.item is not None:
            x = x + self.item(b.item)
        if self.response is not None:
            x = x + self.response(b.response_now.unsqueeze(-1))
        if self.hints is not None:
            x = x + self.hints(b.hints_now.clamp(0, 3))
        return x

    def forward(self, b: Batch) -> torch.Tensor:
        B, T = b.concept.shape
        device = b.concept.device
        pos = torch.arange(T, device=device).unsqueeze(0)
        # keys/values: interactions at positions < t (causal mask excludes t itself)
        x = self._interaction(b) + self.pos(pos)
        if self.time is not None:
            x = x + self.time(torch.stack([b.gap, b.gap_concept], dim=-1))
        x = self.drop(x)
        causal = torch.triu(torch.ones(T, T, device=device, dtype=torch.bool), diagonal=1)
        memory = self.encoder(x, mask=causal, src_key_padding_mask=~b.mask)
        # query: the concept about to be answered, with its exposure count and gaps
        q = self.concept(b.concept) + self.exposure(b.prior_seen.unsqueeze(-1)) + self.pos(pos)
        if self.time is not None:
            q = q + self.time(torch.stack([b.gap, b.gap_concept], dim=-1))
        q = self.query_norm(q)
        # attend strictly to the past, plus a learned start token so the first
        # query (nothing before it) still has a well-defined attention
        mem = torch.cat([self.start.expand(B, 1, -1), memory], dim=1)  # [B, T+1, d]
        strict = torch.ones(T, T + 1, device=device, dtype=torch.bool)
        strict[:, 0] = False
        strict[:, 1:] = torch.triu(torch.ones(T, T, device=device, dtype=torch.bool), diagonal=0)
        kpm = torch.cat([torch.zeros(B, 1, device=device, dtype=torch.bool), ~b.mask], dim=1)
        attended, _ = self.attn(q, mem, mem, attn_mask=strict, key_padding_mask=kpm, need_weights=False)
        if self.forget_rate is not None:
            rate = F.softplus(self.forget_rate(b.concept)).squeeze(-1)  # [B, T] ≥ 0
            decay = torch.exp(-rate * b.gap_concept).unsqueeze(-1)
            attended = attended * decay
        return self.head(torch.cat([q, attended], dim=-1)).squeeze(-1)


# ── the wrapper that gives both models the SequenceModel interface ───────


class NeuralModel:
    """fit / predict / predict_dataset around a torch module, with MC dropout and temperature."""

    def __init__(
        self,
        kind: str,
        n_concepts: int,
        n_items: int,
        config: dict | None = None,
        device: str | None = None,
    ):
        self.kind = kind
        self.n_concepts, self.n_items = n_concepts, n_items
        self.config = config or {}
        if kind == "dkt":
            self.cfg = DKTConfig(**self.config)
            self.net: nn.Module = DKT(n_concepts, self.cfg)
        elif kind == "aquilante":
            self.cfg = AquilanteConfig(**self.config)
            self.net = Aquilante(n_concepts, n_items, self.cfg)
        else:
            raise ValueError(kind)
        self.name = kind
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.net.to(self.device)
        self.temperature = 1.0

    @property
    def max_len(self) -> int:
        return self.cfg.max_len

    def parameters_count(self) -> int:
        return sum(p.numel() for p in self.net.parameters())

    def logits(self, seqs: list[Sequence], train: bool = False) -> tuple[torch.Tensor, Batch]:
        b = make_batch(seqs, self.max_len).to(self.device)
        self.net.train(train)
        return self.net(b), b

    @torch.no_grad()
    def predict_batch(
        self, seqs: list[Sequence], samples: int = 1
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Returns (mean_p, std_p, mask) over MC-dropout samples, on the last `max_len` events."""
        b = make_batch(seqs, self.max_len).to(self.device)
        outs = []
        self.net.train(samples > 1)  # dropout on only when sampling
        for _ in range(samples):
            outs.append(torch.sigmoid(self.net(b) / self.temperature))
        self.net.eval()
        stack = torch.stack(outs)
        return (
            stack.mean(0).cpu().numpy(),
            stack.std(0).cpu().numpy() if samples > 1 else np.zeros(stack.shape[1:]),
            b.mask.cpu().numpy(),
        )

    def predict(self, seq: Sequence) -> np.ndarray:
        mean, _, mask = self.predict_batch([seq])
        out = mean[0][mask[0]]
        if len(out) < len(seq):  # sequence longer than the window: pad the head with the base rate
            out = np.concatenate([np.full(len(seq) - len(out), 0.5), out])
        return out

    def predict_dataset(self, ds: Dataset, batch_size: int = 64) -> tuple[np.ndarray, np.ndarray]:
        ys, ps = [], []
        seqs = sorted(ds.sequences, key=len)
        for i in range(0, len(seqs), batch_size):
            chunk = seqs[i : i + batch_size]
            mean, _, mask = self.predict_batch(chunk)
            for j, s in enumerate(chunk):
                p = mean[j][mask[j]]
                y = s.correct.astype(np.float64)[-len(p) :]
                ys.append(y)
                ps.append(p.astype(np.float64))
        return np.concatenate(ys), np.concatenate(ps)

    def calibrate(self, val: Dataset) -> float:
        """Temperature scaling on the validation set (Guo et al. 2017)."""
        y, logit_list = [], []
        self.net.eval()
        with torch.no_grad():
            for s in val.sequences:
                lg, b = self.logits([s])
                logit_list.append(lg[0][b.mask[0]].cpu())
                y.append(torch.from_numpy(s.correct.astype(np.float32))[-int(b.mask[0].sum()) :])
        if not y:
            return self.temperature
        logits = torch.cat(logit_list)
        target = torch.cat(y)
        log_t = torch.zeros(1, requires_grad=True)
        opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=50)

        def closure():
            opt.zero_grad()
            loss = F.binary_cross_entropy_with_logits(logits / torch.exp(log_t), target)
            loss.backward()
            return loss

        opt.step(closure)
        self.temperature = float(torch.exp(log_t).item())
        return self.temperature

    def state(self) -> dict:
        return {
            "kind": self.kind,
            "n_concepts": self.n_concepts,
            "n_items": self.n_items,
            "config": asdict(self.cfg),
            "temperature": self.temperature,
            "weights": {k: v.cpu() for k, v in self.net.state_dict().items()},
        }

    @classmethod
    def from_state(cls, state: dict, device: str | None = None) -> NeuralModel:
        m = cls(state["kind"], state["n_concepts"], state["n_items"], state["config"], device=device)
        m.net.load_state_dict(state["weights"])
        m.temperature = float(state.get("temperature", 1.0))
        m.net.eval()
        return m

    def params(self) -> dict:
        return {
            **asdict(self.cfg),
            "parameters": self.parameters_count(),
            "temperature": round(self.temperature, 4),
        }


def bce_masked(logits: torch.Tensor, target: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    loss = F.binary_cross_entropy_with_logits(logits, target, reduction="none")
    return (loss * mask).sum() / mask.sum().clamp(min=1)


def set_seed(seed: int) -> None:
    import random  # noqa: PLC0415

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


__all__ = [
    "Aquilante",
    "AquilanteConfig",
    "Batch",
    "DKT",
    "DKTConfig",
    "NeuralModel",
    "bce_masked",
    "make_batch",
    "set_seed",
]
_ = math  # keep import for readers of the docstring formulas
