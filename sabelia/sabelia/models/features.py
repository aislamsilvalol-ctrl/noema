"""The feature-based baselines a knowledge-tracing benchmark has to beat.

Every other baseline in this package models the *concept*. On EdNet a concept
is a tag over 12,056 distinct questions, and the question's own difficulty is
the dataset's strongest single signal — a per-item mean beats the attention
model by 0.078 AUC there. A benchmark that leaves that out is not measuring
what it claims to, and the models in this file exist so it cannot happen
again: a plain logistic regression over eighteen causal features, and a
gradient-boosted version of the same table.

They are deliberately unglamorous. Feature-engineered logistic models have
been the thing to beat in this field for twenty years, and a neural model
that cannot beat one has not earned its parameters.

**Causality.** Every feature is computed from events strictly before the one
being predicted: counts exclude the current event, the response time and the
hints are the *previous* event's, and the target encodings for concept and
item are fitted on the training split alone. `test_features_only_look_backwards`
holds this to it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from sabelia.features.sequences import Dataset, Sequence

#: Smoothing for every rate: a count of one should not read as certainty.
PRIOR = 20.0

COLUMNS = (
    "concept_rate",
    "item_rate",
    "log_gap",
    "log_gap_concept",
    "prior_seen",
    "log_prior_seen",
    "prior_correct",
    "prior_wrong",
    "concept_success",
    "position",
    "log_position",
    "learner_correct",
    "learner_success",
    "previous_correct",
    "last_on_concept",
    "concept_streak",
    "previous_response",
    "previous_hints",
)


def _encode(train: Dataset, key: str) -> tuple[dict[int, float], float]:
    """Smoothed mean outcome per concept or item, from the training split only."""
    total: dict[int, list[float]] = {}
    for s in train.sequences:
        for k, y in zip(getattr(s, key).tolist(), s.correct.tolist(), strict=True):
            total.setdefault(k, [0.0, 0.0])
            total[k][0] += y
            total[k][1] += 1
    everything = np.concatenate([s.correct for s in train.sequences])
    base = float(everything.mean()) if everything.size else 0.5
    return {k: (v[0] + PRIOR * base) / (v[1] + PRIOR) for k, v in total.items()}, base


def build(
    seq: Sequence,
    concept_rate: dict[int, float],
    item_rate: dict[int, float],
    base: float,
) -> np.ndarray:
    """One row of features per event, from what happened before it."""
    n = len(seq)
    correct = seq.correct.astype(np.float64)
    prior_seen = seq.prior_seen.astype(np.float64)
    prior_correct = seq.prior_correct.astype(np.float64)

    previous_correct = np.full(n, base)
    previous_correct[1:] = correct[:-1]
    previous_response = np.zeros(n)
    previous_response[1:] = seq.response_log_ms[:-1]
    previous_hints = np.zeros(n)
    previous_hints[1:] = seq.hints[:-1]

    learner_correct = np.concatenate([[0.0], np.cumsum(correct)[:-1]])
    position = np.arange(n, dtype=np.float64)

    last_on_concept = np.full(n, base)
    concept_streak = np.zeros(n)
    seen_last: dict[int, float] = {}
    streak: dict[int, float] = {}
    for t in range(n):
        c = int(seq.concept[t])
        last_on_concept[t] = seen_last.get(c, base)
        concept_streak[t] = streak.get(c, 0.0)
        if correct[t]:
            streak[c] = streak.get(c, 0.0) + 1
        else:
            streak[c] = 0.0
        seen_last[c] = correct[t]

    return np.column_stack(
        [
            [concept_rate.get(int(c), base) for c in seq.concept],
            [item_rate.get(int(i), base) for i in seq.item],
            seq.log_gap.astype(np.float64),
            seq.log_gap_concept.astype(np.float64),
            prior_seen,
            np.log1p(prior_seen),
            prior_correct,
            prior_seen - prior_correct,
            (prior_correct + PRIOR * base) / (prior_seen + PRIOR),
            position,
            np.log1p(position),
            learner_correct,
            (learner_correct + PRIOR * base) / (position + PRIOR),
            previous_correct,
            last_on_concept,
            concept_streak,
            previous_response,
            previous_hints,
        ]
    )


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.clip(z, -30, 30)))


@dataclass
class FeatureLogistic:
    """Logistic regression over the eighteen features. Newton's method, no library."""

    name: str = "logistic_features"
    steps: int = 40
    l2: float = 1.0
    weights: np.ndarray | None = None
    mean: np.ndarray | None = None
    scale: np.ndarray | None = None
    concept_rate: dict[int, float] = field(default_factory=dict)
    item_rate: dict[int, float] = field(default_factory=dict)
    base: float = 0.5

    def fit(self, train: Dataset, val: Dataset | None = None) -> FeatureLogistic:
        self.concept_rate, self.base = _encode(train, "concept")
        self.item_rate, _ = _encode(train, "item")
        x = np.vstack([self._rows(s) for s in train.sequences])
        y = np.concatenate([s.correct.astype(np.float64) for s in train.sequences])
        self.mean, self.scale = x.mean(0), x.std(0)
        self.scale[self.scale < 1e-9] = 1.0
        design = np.column_stack([(x - self.mean) / self.scale, np.ones(len(y))])
        w = np.zeros(design.shape[1])
        penalty = self.l2 * np.eye(design.shape[1])
        penalty[-1, -1] = 0.0  # never shrink the intercept toward zero
        for _ in range(self.steps):
            p = _sigmoid(design @ w)
            gradient = design.T @ (p - y) + penalty @ w
            s = np.clip(p * (1 - p), 1e-9, None)
            hessian = (design * s[:, None]).T @ design + penalty + 1e-6 * np.eye(len(w))
            step = np.linalg.solve(hessian, gradient)
            w = w - step
            if np.max(np.abs(step)) < 1e-8:
                break
        self.weights = w
        return self

    def _rows(self, seq: Sequence) -> np.ndarray:
        return build(seq, self.concept_rate, self.item_rate, self.base)

    def predict(self, seq: Sequence) -> np.ndarray:
        if self.weights is None:
            raise RuntimeError("fit first")
        x = (self._rows(seq) - self.mean) / self.scale
        return _sigmoid(np.column_stack([x, np.ones(len(seq))]) @ self.weights)

    def predict_dataset(self, ds: Dataset) -> tuple[np.ndarray, np.ndarray]:
        ys = [s.correct.astype(np.float64) for s in ds.sequences]
        ps = [self.predict(s) for s in ds.sequences]
        return np.concatenate(ys), np.concatenate(ps)

    def params(self) -> dict:
        if self.weights is None:
            return {"features": list(COLUMNS)}
        order = np.argsort(-np.abs(self.weights[:-1]))
        return {
            "features": len(COLUMNS),
            "l2": self.l2,
            "strongest": [(COLUMNS[i], round(float(self.weights[i]), 3)) for i in order[:5]],
        }


@dataclass
class GradientBoosting:
    """The same table, boosted. Needs scikit-learn; skipped by the benchmark without it."""

    name: str = "gradient_boosting"
    max_iter: int = 300
    learning_rate: float = 0.05
    model: object | None = None
    concept_rate: dict[int, float] = field(default_factory=dict)
    item_rate: dict[int, float] = field(default_factory=dict)
    base: float = 0.5

    def fit(self, train: Dataset, val: Dataset | None = None) -> GradientBoosting:
        from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: PLC0415

        self.concept_rate, self.base = _encode(train, "concept")
        self.item_rate, _ = _encode(train, "item")
        x = np.vstack([build(s, self.concept_rate, self.item_rate, self.base) for s in train.sequences])
        y = np.concatenate([s.correct.astype(np.float64) for s in train.sequences])
        self.model = HistGradientBoostingClassifier(
            max_iter=self.max_iter,
            learning_rate=self.learning_rate,
            early_stopping=True,
            validation_fraction=0.1,
            random_state=0,
        ).fit(x, y)
        return self

    def predict(self, seq: Sequence) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("fit first")
        x = build(seq, self.concept_rate, self.item_rate, self.base)
        return self.model.predict_proba(x)[:, 1]  # type: ignore[attr-defined]

    def predict_dataset(self, ds: Dataset) -> tuple[np.ndarray, np.ndarray]:
        ys = [s.correct.astype(np.float64) for s in ds.sequences]
        ps = [self.predict(s) for s in ds.sequences]
        return np.concatenate(ys), np.concatenate(ps)

    def params(self) -> dict:
        return {"max_iter": self.max_iter, "learning_rate": self.learning_rate, "features": len(COLUMNS)}
