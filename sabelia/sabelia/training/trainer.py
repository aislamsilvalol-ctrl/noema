"""The training loop for the neural models.

Deterministic where the hardware allows (seeded RNGs, sorted batching),
gradient clipping, early stopping on validation log loss, the best
checkpoint kept, optional mixed precision on CUDA. Configuration is a
dataclass loaded from YAML; nothing is read from environment variables.
"""

from __future__ import annotations

import copy
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import yaml

from sabelia.evaluation.metrics import summarize
from sabelia.features.sequences import Dataset


@dataclass
class TrainConfig:
    model: str = "sabelia"  # "dkt" | "sabelia"
    model_config: dict = field(default_factory=dict)
    seed: int = 0
    epochs: int = 30
    batch_size: int = 32
    lr: float = 1e-3
    weight_decay: float = 1e-4
    grad_clip: float = 1.0
    patience: int = 5
    mixed_precision: bool = False
    calibrate: bool = True
    device: str | None = None
    log_every: int = 1

    @classmethod
    def from_yaml(cls, path: Path) -> TrainConfig:
        return cls(**yaml.safe_load(Path(path).read_text()))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TrainResult:
    model: object
    history: list[dict]
    best_epoch: int
    seconds: float
    val_metrics: dict


def _batches(ds: Dataset, batch_size: int, rng: np.random.Generator):
    """Bucket by length so padding is small, shuffle buckets each epoch."""
    seqs = sorted(ds.sequences, key=len)
    chunks = [seqs[i : i + batch_size] for i in range(0, len(seqs), batch_size)]
    for i in rng.permutation(len(chunks)):
        yield chunks[i]


def train(train_ds: Dataset, val_ds: Dataset, cfg: TrainConfig, *, log=print) -> TrainResult:
    import torch  # noqa: PLC0415

    from sabelia.models.neural import (  # noqa: PLC0415
        NeuralModel,
        Rates,
        bce_masked,
        set_seed,
    )

    set_seed(cfg.seed)
    model = NeuralModel(
        cfg.model,
        train_ds.vocab.n_concepts,
        train_ds.vocab.n_items,
        cfg.model_config,
        device=cfg.device,
    )
    # Difficulty comes from the training split alone, and is carried with the
    # model so validation, test and live inference all see the same table.
    model.rates = Rates.fitted(train_ds)
    opt = torch.optim.AdamW(model.net.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    use_amp = cfg.mixed_precision and model.device.type == "cuda"
    scaler = torch.cuda.amp.GradScaler(enabled=use_amp)
    rng = np.random.default_rng(cfg.seed)

    best_loss, best_state, best_epoch, bad = float("inf"), None, -1, 0
    history: list[dict] = []
    started = time.time()
    for epoch in range(1, cfg.epochs + 1):
        model.net.train()
        total, count = 0.0, 0
        for chunk in _batches(train_ds, cfg.batch_size, rng):
            with torch.autocast(device_type=model.device.type, enabled=use_amp):
                logits, b = model.logits(chunk, train=True)
                loss = bce_masked(logits, b.correct, b.mask.float())
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            if cfg.grad_clip:
                scaler.unscale_(opt)
                torch.nn.utils.clip_grad_norm_(model.net.parameters(), cfg.grad_clip)
            scaler.step(opt)
            scaler.update()
            total += float(loss.item()) * len(chunk)
            count += len(chunk)
        model.net.eval()
        y, p = model.predict_dataset(val_ds)
        val = summarize(y, p) if len(y) else None
        row = {
            "epoch": epoch,
            "train_loss": total / max(count, 1),
            "val_log_loss": val.log_loss if val else float("nan"),
            "val_auc": val.auc if val else float("nan"),
            "seconds": round(time.time() - started, 1),
        }
        history.append(row)
        if epoch % cfg.log_every == 0:
            log(
                log(
                    f"epoch {epoch:3d}  train {row['train_loss']:.4f}  "
                    f"val logloss {row['val_log_loss']:.4f}  auc {row['val_auc']:.4f}"
                )
            )
        if val and val.log_loss < best_loss - 1e-4:
            best_loss, best_epoch, bad = val.log_loss, epoch, 0
            best_state = copy.deepcopy(model.net.state_dict())
        else:
            bad += 1
            if bad >= cfg.patience:
                log(f"early stop at epoch {epoch}; best epoch {best_epoch}")
                break
    if best_state is not None:
        model.net.load_state_dict(best_state)
    model.net.eval()
    if cfg.calibrate and len(val_ds.sequences):
        t = model.calibrate(val_ds)
        log(f"temperature {t:.3f}")
    y, p = model.predict_dataset(val_ds)
    val_metrics = summarize(y, p).as_dict() if len(y) else {}
    return TrainResult(
        model=model,
        history=history,
        best_epoch=best_epoch,
        seconds=time.time() - started,
        val_metrics=val_metrics,
    )


def save_checkpoint(model, path: Path) -> None:
    import torch  # noqa: PLC0415

    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state(), path)


def load_checkpoint(path: Path, device: str | None = None):
    import torch  # noqa: PLC0415

    from sabelia.models.neural import NeuralModel  # noqa: PLC0415

    return NeuralModel.from_state(torch.load(path, map_location="cpu", weights_only=False), device=device)
