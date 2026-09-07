"""A half-life regression forgetting model (after Settles & Meeder 2016).

Recall probability decays exponentially in time measured in half-lives:

    p(recall | Δt) = 2 ** (−Δt / h),    h = 2 ** (θ · x)

where ``x`` are per-concept-per-learner features (right and wrong counts,
the item difficulty when known) and ``θ`` is fitted by gradient descent on
the log loss of recall outcomes against the observed gap. It is the
individualised form of "review at 1, 3, 7, 30 days": the interval comes out
of the learner's own record rather than a fixed table.

Two honest caveats. First, it needs real time gaps; on datasets that only
carry an order (ASSISTments 2009) it degenerates to a per-count model and the
benchmark says so. Second, it is a **recall** model — it predicts whether a
learner will get a concept right after a gap, not whether they understand
it. Aquilante's learner state keeps both.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from aquilante.features.sequences import Dataset, Sequence

MIN_HALF_LIFE_DAYS = 15.0 / 1440.0  # 15 minutes
MAX_HALF_LIFE_DAYS = 274.0  # ~9 months


def recall_probability(half_life_days: float, gap_days: float) -> float:
    h = min(max(half_life_days, MIN_HALF_LIFE_DAYS), MAX_HALF_LIFE_DAYS)
    return float(2.0 ** (-max(gap_days, 0.0) / h))


def _features(prior_right: float, prior_wrong: float, difficulty: float) -> np.ndarray:
    return np.array(
        [
            1.0,
            math.sqrt(1 + prior_right),
            math.sqrt(1 + prior_wrong),
            difficulty if difficulty >= 0 else 0.5,
        ]
    )


@dataclass
class HalfLifeModel:
    """θ over [bias, √(1+right), √(1+wrong), difficulty]; half-life in days = 2^(θ·x)."""

    lr: float = 0.01
    l2: float = 0.1
    epochs: int = 8
    theta: np.ndarray = field(default_factory=lambda: np.array([2.0, 1.0, -0.5, -0.5]))
    fitted_on_real_time: bool = True

    def half_life(self, prior_right: float, prior_wrong: float, difficulty: float = -1.0) -> float:
        h = 2.0 ** float(self.theta @ _features(prior_right, prior_wrong, difficulty))
        return min(max(h, MIN_HALF_LIFE_DAYS), MAX_HALF_LIFE_DAYS)

    def fit(self, train: Dataset) -> HalfLifeModel:
        rows = []
        for s in train.sequences:
            gap = np.expm1(s.log_gap_concept)  # days since last event on this concept
            for t in range(len(s)):
                if s.prior_seen[t] == 0:
                    continue  # nothing to recall yet
                rows.append(
                    (
                        _features(
                            float(s.prior_correct[t]),
                            float(s.prior_seen[t] - s.prior_correct[t]),
                            float(s.difficulty[t]),
                        ),
                        float(gap[t]),
                        float(s.correct[t]),
                    )
                )
        if not rows:
            return self
        X = np.stack([r[0] for r in rows])
        gaps = np.array([r[1] for r in rows])
        y = np.array([r[2] for r in rows])
        # if the dataset carries no real time, gaps collapse to ~0 and the
        # model can only learn a count-based recall; record that fact
        self.fitted_on_real_time = bool(np.median(gaps) > 1e-3)
        gaps = np.maximum(gaps, 1e-3)
        rng = np.random.default_rng(0)
        for _ in range(self.epochs):
            for idx in np.array_split(rng.permutation(len(y)), max(1, len(y) // 2048)):
                h = 2.0 ** (X[idx] @ self.theta)
                h = np.clip(h, MIN_HALF_LIFE_DAYS, MAX_HALF_LIFE_DAYS)
                p = np.clip(2.0 ** (-gaps[idx] / h), 1e-6, 1 - 1e-6)
                # d logloss / d theta = (p - y) * d log p/dθ ; log p = -(gap/h) ln2, dh/dθ = h ln2 x
                dlogp_dtheta = (gaps[idx] / h * math.log(2) ** 2)[:, None] * X[idx]
                # dL/dθ for log loss, with dp/dθ = p · dlog p/dθ
                grad = ((p - y[idx]) / (1 - p + 1e-9))[:, None] * dlogp_dtheta
                grad = np.clip(grad.mean(axis=0), -5, 5) + self.l2 * self.theta * 1e-2
                self.theta -= self.lr * grad
        return self

    def predict(self, seq: Sequence) -> np.ndarray:
        """P(correct) on each event as pure recall of the concept after its gap."""
        gap = np.expm1(seq.log_gap_concept)
        out = np.empty(len(seq))
        for t in range(len(seq)):
            h = self.half_life(
                float(seq.prior_correct[t]),
                float(seq.prior_seen[t] - seq.prior_correct[t]),
                float(seq.difficulty[t]),
            )
            out[t] = recall_probability(h, float(gap[t])) if seq.prior_seen[t] else 0.5
        return out

    def params(self) -> dict:
        return {
            "theta": [round(float(v), 4) for v in self.theta],
            "fitted_on_real_time": self.fitted_on_real_time,
        }
