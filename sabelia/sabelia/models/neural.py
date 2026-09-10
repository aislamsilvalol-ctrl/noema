"""Neural sequence models. ``torch`` is imported here and only here.

Two architectures, both predicting P(correct at t | events < t):

* ``DKT`` — Deep Knowledge Tracing (Piech et al. 2015): a GRU over one-hot
  (concept, correct) interactions. The reference deep baseline.

* ``Sabelia`` — the candidate. A causal self-attention encoder over
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
from dataclasses import asdict, dataclass, field

import numpy as np

from sabelia.features.sequences import Dataset, Sequence
from sabelia.models.features import COLUMNS, build

try:  # torch is optional for the package, required for this module
    import torch
    from torch import nn
    from torch.nn import functional as F  # noqa: N812
except ImportError as exc:  # pragma: no cover
    raise ImportError("sabelia.models.neural needs PyTorch: pip install 'sabelia[torch]'") from exc


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
    #: How often this item and this concept are answered correctly, from the
    #: training split alone. Known before the answer, so it belongs to the
    #: query; without it the model has no way to tell a hard question from an
    #: easy one except through an embedding it has to learn from scratch.
    item_rate: torch.Tensor  # [B, T] float
    concept_rate: torch.Tensor  # [B, T] float
    #: The eighteen causal features of `models.features`, standardised with
    #: the training split's mean and spread. Width zero when the model does
    #: not use them, so the default path pays nothing.
    features: torch.Tensor  # [B, T, F] float
    mask: torch.Tensor  # [B, T] bool: real positions

    def to(self, device) -> Batch:
        return Batch(**{k: v.to(device) for k, v in self.__dict__.items()})


def make_batch(
    seqs: list[Sequence],
    max_len: int,
    rates: Rates | None = None,
    scale: FeatureScale | None = None,
) -> Batch:
    T = min(max_len, max(len(s) for s in seqs))
    rates = rates or Rates()

    if scale is None:
        features = torch.zeros(len(seqs), T, 0)
    else:
        features = torch.zeros(len(seqs), T, len(COLUMNS))
        for i, s in enumerate(seqs):
            table = (build(s, rates.concept, rates.item, rates.base) - scale.mean) / scale.std
            table = table[-T:].astype(np.float32)
            features[i, : len(table)] = torch.from_numpy(table)

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
        item_rate=_pad([rates.for_items(s) for s in seqs], T, np.float32),
        concept_rate=_pad([rates.for_concepts(s) for s in seqs], T, np.float32),
        features=features,
        mask=_pad([np.ones(len(s), dtype=bool) for s in seqs], T, bool, False),
    )


@dataclass
class Rates:
    """Difficulty tables, fitted on the training split and carried with the model."""

    item: dict[int, float] = field(default_factory=dict)
    concept: dict[int, float] = field(default_factory=dict)
    base: float = 0.5

    def for_items(self, seq: Sequence) -> np.ndarray:
        return np.array([self.item.get(int(i), self.base) for i in seq.item], dtype=np.float32)

    def for_concepts(self, seq: Sequence) -> np.ndarray:
        return np.array([self.concept.get(int(c), self.base) for c in seq.concept], dtype=np.float32)

    def as_dict(self) -> dict:
        return {"item": self.item, "concept": self.concept, "base": self.base}

    @classmethod
    def fitted(cls, train) -> Rates:
        from sabelia.models.features import _encode  # noqa: PLC0415

        item, base = _encode(train, "item")
        concept, _ = _encode(train, "concept")
        return cls(item=item, concept=concept, base=base)


@dataclass
class FeatureScale:
    """Mean and spread of the feature table on the training split."""

    mean: np.ndarray
    std: np.ndarray

    @classmethod
    def fitted(cls, train, rates: Rates) -> FeatureScale:
        x = np.vstack([build(s, rates.concept, rates.item, rates.base) for s in train.sequences])
        std = x.std(0)
        std[std < 1e-9] = 1.0
        return cls(mean=x.mean(0), std=std)

    def as_dict(self) -> dict:
        return {"mean": self.mean.tolist(), "std": self.std.tolist()}


# ── configs ──────────────────────────────────────────────────────────────


@dataclass
class DKTConfig:
    hidden: int = 64
    dropout: float = 0.2
    max_len: int = 200


@dataclass
class SabeliaConfig:
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
    #: The difficulty of the question being asked, as a number rather than as
    #: an embedding to be discovered. A per-item mean alone beats this model
    #: by 0.078 AUC on EdNet, so the signal is there and the model was not
    #: reading it.
    use_difficulty: bool = True
    #: The whole feature table as a logistic term added to the network's
    #: logit, so the network is asked only for what the counts cannot say.
    #: Off until a benchmark says it pays; `sabelia-hybrid` measures it.
    use_features: bool = False
    #: Off by default since 2026-09-09: an item embedding is the only ablation
    #: that ever moved the same way on every seed of a dataset, and it moved
    #: *against* keeping it — +0.0033 AUC on all three Duolingo seeds, and
    #: five of six seeds across Duolingo and EdNet. It is also most of the
    #: model: 862k parameters against 90k without it. Set it back to True to
    #: reproduce anything published before that date.
    use_item: bool = False


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


# ── Sabelia ────────────────────────────────────────────────────────────


class Sabelia(nn.Module):
    name = "sabelia"

    def __init__(self, n_concepts: int, n_items: int, cfg: SabeliaConfig):
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
        self.difficulty = (
            nn.Sequential(nn.Linear(2, d), nn.GELU(), nn.Linear(d, d)) if cfg.use_difficulty else None
        )
        self.feature_head = nn.Linear(len(COLUMNS), 1) if cfg.use_features else None
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
        if self.difficulty is not None:
            # what is being asked, not how it went: safe in the query
            q = q + self.difficulty(torch.stack([b.item_rate, b.concept_rate], dim=-1))
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
        logit = self.head(torch.cat([q, attended], dim=-1)).squeeze(-1)
        if self.feature_head is not None:
            logit = logit + self.feature_head(b.features).squeeze(-1)
        return logit


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
        elif kind == "sabelia":
            self.cfg = SabeliaConfig(**self.config)
            self.net = Sabelia(n_concepts, n_items, self.cfg)
        else:
            raise ValueError(kind)
        self.name = kind
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.net.to(self.device)
        self.temperature = 1.0
        self.rates = Rates()
        self.scale: FeatureScale | None = None

    @property
    def max_len(self) -> int:
        return self.cfg.max_len

    def parameters_count(self) -> int:
        return sum(p.numel() for p in self.net.parameters())

    def logits(self, seqs: list[Sequence], train: bool = False) -> tuple[torch.Tensor, Batch]:
        b = make_batch(seqs, self.max_len, self.rates, self.scale).to(self.device)
        self.net.train(train)
        return self.net(b), b

    @torch.no_grad()
    def predict_batch(
        self, seqs: list[Sequence], samples: int = 1
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Returns (mean_p, std_p, mask) over MC-dropout samples, on the last `max_len` events."""
        b = make_batch(seqs, self.max_len, self.rates, self.scale).to(self.device)
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

    def _window_plan(self, total: int) -> list[tuple[int, int, int]]:
        """(start, end, keep_from) for each window of a sequence longer than `max_len`.

        Windows overlap by half; each keeps only the part it has real history
        for, and the first keeps everything.
        """
        plan: list[tuple[int, int, int]] = []
        step = max(1, self.max_len // 2)
        filled = start = 0
        while filled < total:
            end = min(start + self.max_len, total)
            plan.append((start, end, filled))
            filled = end
            if end == total:
                break
            start = min(start + step, total - self.max_len)
        return plan

    def _predict_long(self, seqs: list[Sequence], batch_size: int = 64) -> list[np.ndarray]:
        """Every event of every long sequence, with all their windows batched together.

        Predicting a long learner one window per forward pass is what made each
        epoch's validation cost more than the epoch's training on EdNet: 24
        long validation sequences took 7.5 s of an 18 s epoch in a profile.
        The windows are independent given their inputs, so they batch.
        """
        jobs = [
            (i, start, end, keep)
            for i, s in enumerate(seqs)
            for start, end, keep in self._window_plan(len(s))
        ]
        out = [np.empty(len(s), dtype=np.float64) for s in seqs]
        for j in range(0, len(jobs), batch_size):
            chunk = jobs[j : j + batch_size]
            mean, _, mask = self.predict_batch([seqs[i].window(a, b) for i, a, b, _ in chunk])
            for k, (i, a, b, keep) in enumerate(chunk):
                out[i][keep:b] = mean[k][mask[k]][keep - a :]
        return out

    def predict(self, seq: Sequence) -> np.ndarray:
        """One probability per event, for a sequence of any length."""
        if len(seq) <= self.max_len:
            mean, _, mask = self.predict_batch([seq])
            return mean[0][mask[0]].astype(np.float64)
        return self._predict_long([seq])[0]

    def predict_dataset(self, ds: Dataset, batch_size: int = 64) -> tuple[np.ndarray, np.ndarray]:
        """Every event of every sequence, so the score covers what the baselines' does."""
        ys, ps = [], []
        short = sorted((s for s in ds.sequences if len(s) <= self.max_len), key=len)
        for i in range(0, len(short), batch_size):
            chunk = short[i : i + batch_size]
            mean, _, mask = self.predict_batch(chunk)
            for j, s in enumerate(chunk):
                p = mean[j][mask[j]]
                ys.append(s.correct.astype(np.float64)[-len(p) :])
                ps.append(p.astype(np.float64))
        long = [s for s in ds.sequences if len(s) > self.max_len]
        for s, p in zip(long, self._predict_long(long, batch_size), strict=True):
            ys.append(s.correct.astype(np.float64))
            ps.append(p)
        if not ys:
            return np.array([]), np.array([])
        return np.concatenate(ys), np.concatenate(ps)

    def calibrate(self, val: Dataset) -> float:
        """Temperature scaling on the validation set (Guo et al. 2017).

        Fitted on every validation event, through the same windowed path the
        score uses. It used to see only each learner's last window, so the
        temperature was tuned on the recent, easier part of the history.
        """
        saved, self.temperature = self.temperature, 1.0
        y_np, p_np = self.predict_dataset(val)
        self.temperature = saved
        if not len(y_np):
            return self.temperature
        p_np = np.clip(p_np, 1e-6, 1 - 1e-6)
        logits = torch.from_numpy(np.log(p_np / (1 - p_np)).astype(np.float32))
        target = torch.from_numpy(y_np.astype(np.float32))
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
            "rates": self.rates.as_dict(),
            "scale": None if self.scale is None else self.scale.as_dict(),
            "weights": {k: v.cpu() for k, v in self.net.state_dict().items()},
        }

    @classmethod
    def from_state(cls, state: dict, device: str | None = None) -> NeuralModel:
        m = cls(state["kind"], state["n_concepts"], state["n_items"], state["config"], device=device)
        m.net.load_state_dict(state["weights"])
        m.temperature = float(state.get("temperature", 1.0))
        saved = state.get("rates") or {}
        m.rates = Rates(
            item={int(k): float(v) for k, v in (saved.get("item") or {}).items()},
            concept={int(k): float(v) for k, v in (saved.get("concept") or {}).items()},
            base=float(saved.get("base", 0.5)),
        )
        if state.get("scale"):
            m.scale = FeatureScale(
                mean=np.asarray(state["scale"]["mean"]), std=np.asarray(state["scale"]["std"])
            )
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
    "Sabelia",
    "SabeliaConfig",
    "Batch",
    "DKT",
    "DKTConfig",
    "NeuralModel",
    "bce_masked",
    "make_batch",
    "set_seed",
]
_ = math  # keep import for readers of the docstring formulas
