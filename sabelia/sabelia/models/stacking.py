"""A blend of models, weighted on held-out learners.

On EdNet the attention model and BKT are wrong in different places: Sabelia
predicts a learner's *first* attempt at a concept better, where there are no
counts for a Bayesian model to work from, and BKT predicts the later ones
better, where the counts are the whole story. Neither ordering is an accident
of a seed — it follows from what each model reads — and a blend of the two
beats both on ranking and on log loss.

The blend is a logistic regression on the components' log-odds, fitted on a
validation split the components never trained on, because weights fitted on
the training set would reward whichever component memorised it. There is no
hidden layer and no feature engineering: with two or three components the
weights are readable, and a component that adds nothing gets a weight near
zero and says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from sabelia.features.sequences import Dataset, Sequence

EPS = 1e-6


def logit(p: np.ndarray) -> np.ndarray:
    return np.log(np.clip(p, EPS, 1 - EPS) / (1 - np.clip(p, EPS, 1 - EPS)))


def sigmoid(z: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.clip(z, -30, 30)))


def fit_logistic(x: np.ndarray, y: np.ndarray, *, steps: int = 200) -> np.ndarray:
    """Newton's method on the log loss. Returns weights with the intercept last."""
    design = np.column_stack([x, np.ones(len(y))])
    w = np.zeros(design.shape[1])
    for _ in range(steps):
        p = sigmoid(design @ w)
        gradient = design.T @ (p - y)
        s = np.clip(p * (1 - p), 1e-9, None)
        hessian = (design * s[:, None]).T @ design + 1e-6 * np.eye(design.shape[1])
        step = np.linalg.solve(hessian, gradient)
        w = w - step
        if np.max(np.abs(step)) < 1e-9:
            break
    return w


@dataclass
class Stacked:
    """Several fitted models, blended by weights learned on a held-out split.

    The components are already fitted: this does not train them, and it must
    not be given the split they were trained on. `name` follows the components
    so a benchmark row says what was blended.
    """

    models: list = field(default_factory=list)
    weights: np.ndarray | None = None
    name: str = "stack"

    def fit(self, val: Dataset) -> Stacked:
        y, features = self._features(val)
        self.weights = fit_logistic(features, y)
        return self

    def _features(self, ds: Dataset) -> tuple[np.ndarray, np.ndarray]:
        ys = [np.concatenate([s.correct.astype(np.float64) for s in ds.sequences])]
        columns = [
            logit(np.concatenate([np.asarray(m.predict(s), dtype=np.float64) for s in ds.sequences]))
            for m in self.models
        ]
        return ys[0], np.column_stack(columns)

    def predict(self, seq: Sequence) -> np.ndarray:
        if self.weights is None:
            raise RuntimeError("fit the blend on a held-out split first")
        columns = [logit(np.asarray(m.predict(seq), dtype=np.float64)) for m in self.models]
        design = np.column_stack([*columns, np.ones(len(seq))])
        return sigmoid(design @ self.weights)

    def predict_dataset(self, ds: Dataset) -> tuple[np.ndarray, np.ndarray]:
        ys, ps = [], []
        for s in ds.sequences:
            ys.append(s.correct.astype(np.float64))
            ps.append(self.predict(s))
        return np.concatenate(ys), np.concatenate(ps)

    def params(self) -> dict:
        weights = [] if self.weights is None else [round(float(w), 4) for w in self.weights]
        return {
            "components": [getattr(m, "name", type(m).__name__) for m in self.models],
            "weights": weights[:-1],
            "intercept": weights[-1] if weights else None,
        }
