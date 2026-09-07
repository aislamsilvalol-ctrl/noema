"""Baselines. Without them a neural result means nothing.

All models share one interface: ``fit(dataset)`` then ``predict(sequence)``
returning, for every graded event ``t`` in the sequence, the probability that
it is correct **given only events before ``t``**. That is the knowledge
tracing task; every metric in the benchmark is computed on these
next-step predictions, pooled over the test learners.

* ``GlobalMean`` — the base rate. The floor.
* ``ConceptMean`` — the base rate per concept (an item-difficulty-only model).
* ``MasteryHeuristic`` — what most products ship: a recency-weighted running
  accuracy per concept, shrunk toward the concept mean. This is close to the
  ``project()`` rule Noema's Professor Engine uses today.
* ``PFA`` — Performance Factors Analysis (Pavlik, Cen & Koedinger 2009): a
  logistic regression on concept difficulty, prior successes and prior
  failures. Simple, interpretable, and often within a few AUC points of
  deep models on small data.
* ``BKT`` — Bayesian Knowledge Tracing (Corbett & Anderson 1995), one
  two-state HMM per concept with parameters (prior, learn, guess, slip)
  fitted by expectation-maximisation. No forgetting by design; the
  ``forget`` option adds the standard extension.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from sabelia.features.sequences import Dataset, Sequence


class SequenceModel:
    """The interface every model implements."""

    name: str = "model"

    def fit(self, train: Dataset, val: Dataset | None = None) -> SequenceModel:
        raise NotImplementedError

    def predict(self, seq: Sequence) -> np.ndarray:
        """P(correct) for each position, using only earlier positions."""
        raise NotImplementedError

    def predict_dataset(self, ds: Dataset) -> tuple[np.ndarray, np.ndarray]:
        ys, ps = [], []
        for s in ds.sequences:
            ys.append(s.correct.astype(np.float64))
            ps.append(np.asarray(self.predict(s), dtype=np.float64))
        if not ys:
            return np.array([]), np.array([])
        return np.concatenate(ys), np.concatenate(ps)

    def params(self) -> dict:
        return {}


@dataclass
class GlobalMean(SequenceModel):
    name: str = "global_mean"
    p: float = 0.5

    def fit(self, train: Dataset, val: Dataset | None = None):
        c = np.concatenate([s.correct for s in train.sequences])
        self.p = float(c.mean()) if c.size else 0.5
        return self

    def predict(self, seq: Sequence) -> np.ndarray:
        return np.full(len(seq), self.p)


@dataclass
class ConceptMean(SequenceModel):
    name: str = "concept_mean"
    prior_strength: float = 5.0
    means: dict[int, float] = field(default_factory=dict)
    p: float = 0.5

    def fit(self, train: Dataset, val: Dataset | None = None):
        tot: dict[int, list[float]] = {}
        for s in train.sequences:
            for c, y in zip(s.concept.tolist(), s.correct.tolist(), strict=True):
                tot.setdefault(c, [0.0, 0.0])
                tot[c][0] += y
                tot[c][1] += 1
        all_c = np.concatenate([s.correct for s in train.sequences])
        self.p = float(all_c.mean()) if all_c.size else 0.5
        k = self.prior_strength
        self.means = {c: (v[0] + k * self.p) / (v[1] + k) for c, v in tot.items()}
        return self

    def predict(self, seq: Sequence) -> np.ndarray:
        return np.array([self.means.get(int(c), self.p) for c in seq.concept])


@dataclass
class MasteryHeuristic(SequenceModel):
    """Recency-weighted running accuracy per concept, shrunk to the concept mean."""

    name: str = "mastery_heuristic"
    decay: float = 0.75
    prior_strength: float = 2.0
    concept_prior: ConceptMean = field(default_factory=ConceptMean)

    def fit(self, train: Dataset, val: Dataset | None = None):
        self.concept_prior.fit(train)
        return self

    def predict(self, seq: Sequence) -> np.ndarray:
        num: dict[int, float] = {}
        den: dict[int, float] = {}
        out = np.empty(len(seq))
        for t, (c, y) in enumerate(zip(seq.concept.tolist(), seq.correct.tolist(), strict=True)):
            prior = self.concept_prior.means.get(c, self.concept_prior.p)
            n, d = num.get(c, 0.0), den.get(c, 0.0)
            out[t] = (n + self.prior_strength * prior) / (d + self.prior_strength)
            num[c] = self.decay * n + y
            den[c] = self.decay * d + 1.0
        return out

    def params(self) -> dict:
        return {"decay": self.decay, "prior_strength": self.prior_strength}


@dataclass
class PFA(SequenceModel):
    """Performance Factors Analysis: logit p = beta_c + gamma_c * successes + rho_c * failures.

    Fitted by L2-regularised gradient descent on the pooled training events.
    Per-concept coefficients shrink toward global ones (a simple hierarchical prior).
    """

    name: str = "pfa"
    l2: float = 0.05
    epochs: int = 30
    lr: float = 0.5
    beta: np.ndarray | None = None
    gamma: np.ndarray | None = None
    rho: np.ndarray | None = None

    def _features(self, seq: Sequence) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        c = seq.concept
        s = seq.prior_correct.astype(np.float64)
        f = (seq.prior_seen - seq.prior_correct).astype(np.float64)
        return c, np.log1p(s), np.log1p(f)

    def fit(self, train: Dataset, val: Dataset | None = None):
        n = train.vocab.n_concepts
        rows = [(*self._features(s), s.correct.astype(np.float64)) for s in train.sequences]
        C = np.concatenate([r[0] for r in rows])
        S = np.concatenate([r[1] for r in rows])
        F = np.concatenate([r[2] for r in rows])
        Y = np.concatenate([r[3] for r in rows])
        # global coefficients first (a few passes), then per-concept offsets shrunk to them
        g = np.zeros(3)
        for _ in range(self.epochs):
            logit = g[0] + g[1] * S + g[2] * F
            p = 1 / (1 + np.exp(-logit))
            err = p - Y
            g -= self.lr * np.array([err.mean(), (err * S).mean(), (err * F).mean()])
        self.beta = np.full(n, g[0])
        self.gamma = np.full(n, g[1])
        self.rho = np.full(n, g[2])
        rng = np.random.default_rng(0)
        for _ in range(self.epochs):
            order = rng.permutation(len(Y))
            for start in range(0, len(Y), 4096):
                idx = order[start : start + 4096]
                c, s, f, y = C[idx], S[idx], F[idx], Y[idx]
                logit = np.clip(self.beta[c] + self.gamma[c] * s + self.rho[c] * f, -12, 12)
                p = 1 / (1 + np.exp(-logit))
                err = p - y
                # mean gradient per concept, so a frequent concept does not take giant steps
                counts = np.bincount(c, minlength=n).astype(float) + 1.0
                step = self.lr / counts
                np.add.at(self.beta, c, -step[c] * (err + self.l2 * (self.beta[c] - g[0])))
                np.add.at(self.gamma, c, -step[c] * (err * s + self.l2 * (self.gamma[c] - g[1])))
                np.add.at(self.rho, c, -step[c] * (err * f + self.l2 * (self.rho[c] - g[2])))
        return self

    def predict(self, seq: Sequence) -> np.ndarray:
        assert self.beta is not None and self.gamma is not None and self.rho is not None
        c, s, f = self._features(seq)
        c = np.where(c < len(self.beta), c, 1)
        logit = self.beta[c] + self.gamma[c] * s + self.rho[c] * f
        return 1 / (1 + np.exp(-logit))

    def params(self) -> dict:
        return {"l2": self.l2, "epochs": self.epochs, "lr": self.lr}


@dataclass
class BKT(SequenceModel):
    """Bayesian Knowledge Tracing, one HMM per concept, fitted by EM.

    States: unknown/known. Parameters per concept: P(L0) prior, P(T) learn,
    P(G) guess, P(S) slip, and optionally P(F) forget. Predictions use the
    filtered belief before observing the current answer:
    ``P(correct) = P(known)(1-S) + (1-P(known))G``.
    """

    name: str = "bkt"
    em_iters: int = 20
    forget: bool = False
    params_by_concept: dict[int, tuple[float, float, float, float, float]] = field(default_factory=dict)
    default: tuple[float, float, float, float, float] = (0.3, 0.15, 0.2, 0.1, 0.0)

    def fit(self, train: Dataset, val: Dataset | None = None):
        # gather per-concept observation runs (each learner's sub-sequence on that concept)
        runs: dict[int, list[np.ndarray]] = {}
        for s in train.sequences:
            for c in np.unique(s.concept):
                runs.setdefault(int(c), []).append(s.correct[s.concept == c].astype(np.float64))
        for c, obs in runs.items():
            self.params_by_concept[c] = self._em(obs)
        return self

    def _em(self, runs: list[np.ndarray]) -> tuple[float, float, float, float, float]:
        def emit(k: int, yt: float, G: float, S: float) -> float:
            return (G if yt else 1 - G) if k == 0 else ((1 - S) if yt else S)

        L0, T, G, S, F = self.default
        F = 0.05 if self.forget else 0.0
        for _ in range(self.em_iters):
            n_l0 = d_l0 = 0.0
            n_t = d_t = 0.0
            n_g = d_g = 0.0
            n_s = d_s = 0.0
            n_f = d_f = 0.0
            for y in runs:
                n = len(y)
                # forward
                alpha = np.zeros((n, 2))  # [unknown, known]
                alpha[0] = [(1 - L0) * emit(0, y[0], G, S), L0 * emit(1, y[0], G, S)]
                alpha[0] /= alpha[0].sum() + 1e-12
                for t in range(1, n):
                    u = alpha[t - 1, 0] * (1 - T) + alpha[t - 1, 1] * F
                    k = alpha[t - 1, 0] * T + alpha[t - 1, 1] * (1 - F)
                    alpha[t] = [u * emit(0, y[t], G, S), k * emit(1, y[t], G, S)]
                    alpha[t] /= alpha[t].sum() + 1e-12
                # backward
                beta = np.ones((n, 2))
                for t in range(n - 2, -1, -1):
                    bu = (1 - T) * emit(0, y[t + 1], G, S) * beta[t + 1, 0] + T * emit(
                        1, y[t + 1], G, S
                    ) * beta[t + 1, 1]
                    bk = (
                        F * emit(0, y[t + 1], G, S) * beta[t + 1, 0]
                        + (1 - F) * emit(1, y[t + 1], G, S) * beta[t + 1, 1]
                    )
                    beta[t] = [bu, bk]
                    beta[t] /= beta[t].sum() + 1e-12
                gamma = alpha * beta
                gamma /= gamma.sum(axis=1, keepdims=True) + 1e-12
                n_l0 += gamma[0, 1]
                d_l0 += 1
                for t in range(n):
                    n_g += gamma[t, 0] * y[t]
                    d_g += gamma[t, 0]
                    n_s += gamma[t, 1] * (1 - y[t])
                    d_s += gamma[t, 1]
                for t in range(n - 1):
                    # xi: P(unknown_t, known_{t+1})
                    num_t = alpha[t, 0] * T * emit(1, y[t + 1], G, S) * beta[t + 1, 1]
                    den_t = alpha[t, 0] * (
                        (1 - T) * emit(0, y[t + 1], G, S) * beta[t + 1, 0]
                        + T * emit(1, y[t + 1], G, S) * beta[t + 1, 1]
                    )
                    if den_t > 0:
                        n_t += num_t / den_t * gamma[t, 0]
                        d_t += gamma[t, 0]
                    if self.forget:
                        num_f = alpha[t, 1] * F * emit(0, y[t + 1], G, S) * beta[t + 1, 0]
                        den_f = alpha[t, 1] * (
                            F * emit(0, y[t + 1], G, S) * beta[t + 1, 0]
                            + (1 - F) * emit(1, y[t + 1], G, S) * beta[t + 1, 1]
                        )
                        if den_f > 0:
                            n_f += num_f / den_f * gamma[t, 1]
                            d_f += gamma[t, 1]
            L0 = float(np.clip(n_l0 / max(d_l0, 1e-9), 0.01, 0.99))
            T = float(np.clip(n_t / max(d_t, 1e-9), 0.01, 0.99))
            G = float(np.clip(n_g / max(d_g, 1e-9), 0.01, 0.5))  # the usual bounds against degenerate fits
            S = float(np.clip(n_s / max(d_s, 1e-9), 0.01, 0.5))
            if self.forget:
                F = float(np.clip(n_f / max(d_f, 1e-9), 0.0, 0.5))
        return (L0, T, G, S, F)

    def predict(self, seq: Sequence) -> np.ndarray:
        belief: dict[int, float] = {}
        out = np.empty(len(seq))
        for t, (c, y) in enumerate(zip(seq.concept.tolist(), seq.correct.tolist(), strict=True)):
            L0, T, G, S, F = self.params_by_concept.get(c, self.default)
            k = belief.get(c, L0)
            out[t] = k * (1 - S) + (1 - k) * G
            # posterior after observing y, then learning transition
            if y:
                post = k * (1 - S) / (k * (1 - S) + (1 - k) * G + 1e-12)
            else:
                post = k * S / (k * S + (1 - k) * (1 - G) + 1e-12)
            belief[c] = post + (1 - post) * T - post * F
        return out

    def params(self) -> dict:
        return {"em_iters": self.em_iters, "forget": self.forget}


@dataclass
class DAS3H(SequenceModel):
    """A DAS3H-style time-window logistic model (Choffin et al. 2019).

    logit p = beta_c + Σ_w [ theta_w · log1p(wins_w) + phi_w · log1p(fails_w) ]

    where the windows are the past 1 hour, 1 day, 7 days, 30 days and all
    time, and wins/fails count the learner's earlier successes and failures
    on the *same concept* inside each window. Forgetting enters as the
    difference between the windows: a success a month ago counts in the
    ∞ window but not in the 1-day one. Global window coefficients, per-
    concept intercepts shrunk to a global one. On a dataset without real
    timestamps every window collapses onto the ∞ window and the model
    degenerates to PFA; the benchmark says so through its metrics.
    """

    name: str = "das3h"
    windows_days: tuple[float, ...] = (1 / 24, 1.0, 7.0, 30.0, float("inf"))
    l2: float = 0.05
    epochs: int = 30
    lr: float = 0.3
    beta: np.ndarray | None = None
    theta: np.ndarray | None = None
    phi: np.ndarray | None = None
    g0: float = 0.0

    def _features(self, seq: Sequence) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Per event: concept, log1p wins per window, log1p fails per window (only earlier events)."""
        W = len(self.windows_days)
        wins = np.zeros((len(seq), W))
        fails = np.zeros((len(seq), W))
        history: dict[int, list[tuple[float, int]]] = {}
        for t in range(len(seq)):
            c = int(seq.concept[t])
            now = float(seq.timestamp[t])
            past = history.get(c, [])
            for ts, y in past:
                age_days = (now - ts) / 86400.0
                for w, width in enumerate(self.windows_days):
                    if age_days <= width:
                        if y:
                            wins[t, w] += 1
                        else:
                            fails[t, w] += 1
            history.setdefault(c, []).append((now, int(seq.correct[t])))
        return seq.concept, np.log1p(wins), np.log1p(fails)

    def fit(self, train: Dataset, val: Dataset | None = None):
        n = train.vocab.n_concepts
        W = len(self.windows_days)
        rows = [(*self._features(s), s.correct.astype(np.float64)) for s in train.sequences]
        C = np.concatenate([r[0] for r in rows])
        Wn = np.concatenate([r[1] for r in rows])
        Fl = np.concatenate([r[2] for r in rows])
        Y = np.concatenate([r[3] for r in rows])
        self.theta = np.zeros(W)
        self.phi = np.zeros(W)
        self.g0 = 0.0
        self.beta = np.zeros(n)
        rng = np.random.default_rng(0)
        for _ in range(self.epochs):
            order = rng.permutation(len(Y))
            for start in range(0, len(Y), 4096):
                idx = order[start : start + 4096]
                c, wn, fl, y = C[idx], Wn[idx], Fl[idx], Y[idx]
                logit = np.clip(self.g0 + self.beta[c] + wn @ self.theta + fl @ self.phi, -12, 12)
                p = 1 / (1 + np.exp(-logit))
                err = p - y
                self.g0 -= self.lr * err.mean()
                self.theta -= self.lr * ((err[:, None] * wn).mean(axis=0) + self.l2 * self.theta * 0.1)
                self.phi -= self.lr * ((err[:, None] * fl).mean(axis=0) + self.l2 * self.phi * 0.1)
                counts = np.bincount(c, minlength=n).astype(float) + 1.0
                step = self.lr / counts
                np.add.at(self.beta, c, -step[c] * (err + self.l2 * self.beta[c]))
        return self

    def predict(self, seq: Sequence) -> np.ndarray:
        assert self.beta is not None and self.theta is not None and self.phi is not None
        c, wn, fl = self._features(seq)
        c = np.where(c < len(self.beta), c, 1)
        logit = self.g0 + self.beta[c] + wn @ self.theta + fl @ self.phi
        return 1 / (1 + np.exp(-np.clip(logit, -12, 12)))

    def params(self) -> dict:
        return {
            "windows_days": [w if w != float("inf") else "inf" for w in self.windows_days],
            "l2": self.l2,
            "epochs": self.epochs,
            "lr": self.lr,
            "theta": None if self.theta is None else [round(float(v), 3) for v in self.theta],
            "phi": None if self.phi is None else [round(float(v), 3) for v in self.phi],
        }


def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))
