"""Metrics, implemented here so evaluation has no optional dependency.

Accuracy is reported but is not the headline: knowledge tracing datasets are
~65-75 % correct, so a constant predictor scores well on it. The metrics that
matter for pedagogical decisions are discrimination (AUC), the quality of the
probabilities (log loss, Brier) and whether an 80 % means 80 % (ECE).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


def _as_arrays(y_true, y_prob) -> tuple[np.ndarray, np.ndarray]:
    y = np.asarray(y_true, dtype=np.float64).ravel()
    p = np.clip(np.asarray(y_prob, dtype=np.float64).ravel(), 1e-7, 1 - 1e-7)
    if y.shape != p.shape:
        raise ValueError(f"shape mismatch: {y.shape} vs {p.shape}")
    return y, p


def auc(y_true, y_prob) -> float:
    """ROC AUC by the Mann-Whitney U statistic, with tie handling."""
    y, p = _as_arrays(y_true, y_prob)
    pos = y == 1
    n_pos, n_neg = int(pos.sum()), int((~pos).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    order = p.argsort()
    ranks = np.empty_like(order, dtype=np.float64)
    # average ranks for ties
    sorted_p = p[order]
    i = 0
    while i < len(sorted_p):
        j = i
        while j + 1 < len(sorted_p) and sorted_p[j + 1] == sorted_p[i]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def log_loss(y_true, y_prob) -> float:
    y, p = _as_arrays(y_true, y_prob)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(y_true, y_prob) -> float:
    y, p = _as_arrays(y_true, y_prob)
    return float(np.mean((p - y) ** 2))


def accuracy(y_true, y_prob, threshold: float = 0.5) -> float:
    y, p = _as_arrays(y_true, y_prob)
    return float(np.mean((p >= threshold) == (y == 1)))


def reliability_table(y_true, y_prob, bins: int = 10) -> list[dict[str, float]]:
    """Per-bin mean predicted probability, observed frequency and count."""
    y, p = _as_arrays(y_true, y_prob)
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    rows = []
    for b in range(bins):
        mask = idx == b
        n = int(mask.sum())
        rows.append(
            {
                "bin_lower": float(edges[b]),
                "bin_upper": float(edges[b + 1]),
                "count": n,
                "mean_predicted": float(p[mask].mean()) if n else float("nan"),
                "observed": float(y[mask].mean()) if n else float("nan"),
            }
        )
    return rows


def expected_calibration_error(y_true, y_prob, bins: int = 10) -> float:
    y, p = _as_arrays(y_true, y_prob)
    total = len(p)
    if total == 0:
        return float("nan")
    ece = 0.0
    for row in reliability_table(y, p, bins):
        if row["count"]:
            ece += row["count"] / total * abs(row["observed"] - row["mean_predicted"])
    return float(ece)


@dataclass(frozen=True)
class Metrics:
    n: int
    auc: float
    log_loss: float
    brier: float
    ece: float
    accuracy: float
    base_rate: float

    def as_dict(self) -> dict[str, float]:
        return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def summarize(y_true, y_prob, bins: int = 10) -> Metrics:
    y, p = _as_arrays(y_true, y_prob)
    return Metrics(
        n=int(len(y)),
        auc=auc(y, p),
        log_loss=log_loss(y, p),
        brier=brier(y, p),
        ece=expected_calibration_error(y, p, bins),
        accuracy=accuracy(y, p),
        base_rate=float(y.mean()) if len(y) else float("nan"),
    )
