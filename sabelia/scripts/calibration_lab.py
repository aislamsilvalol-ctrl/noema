"""Where Sabelia's probabilities go wrong, and what fixes them.

.venv/bin/python scripts/calibration_lab.py --dataset configs/datasets/ednet-kt1-sample.yaml --seed 0

Sabelia ranks better than every baseline on EdNet and assigns worse
probabilities than BKT. The training loop already does the two obvious
things — it early-stops on validation log loss and fits a temperature — so
the miscalibration left over is not global over-confidence. This script
finds out what it is instead, and tries four fixes on the same split:

* **temperature** — one scalar, what ships today.
* **Platt** — a slope *and* an intercept on the logit, which can move the
  base rate as well as the confidence.
* **isotonic** — any monotone map, fitted by pool-adjacent-violators. It can
  correct a curve that is over-confident in one region and under-confident in
  another, which a single scalar cannot.
* **stack** — a logistic blend of Sabelia's logit with BKT's and PFA's. If a
  1995 Bayesian model knows something about this learner's probability that
  the attention model does not, this is what recovers it.

Every calibrator is fitted on validation and scored on test, so nothing here
reports a number that saw its own answer. The stratified table says where the
loss lives: the first attempts at a concept, or the later ones.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import yaml

from sabelia.data.adapters import load_dataset
from sabelia.evaluation.metrics import summarize
from sabelia.features.sequences import Dataset, split_by_student
from sabelia.models.baselines import BKT, PFA

EPS = 1e-6


def logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def sigmoid(z: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.clip(z, -30, 30)))


def predictions(model, ds: Dataset) -> tuple[np.ndarray, np.ndarray]:
    """(y, p) in the dataset's own order, for any model with `predict`."""
    ys, ps = [], []
    for s in ds.sequences:
        ys.append(s.correct.astype(np.float64))
        ps.append(np.asarray(model.predict(s), dtype=np.float64))
    return np.concatenate(ys), np.concatenate(ps)


def prior_attempts(ds: Dataset) -> np.ndarray:
    """How many times this learner had met this concept before each event."""
    return np.concatenate([s.prior_seen.astype(np.int64) for s in ds.sequences])


# ── calibrators: fitted on validation, applied to test ─────────────────────


def fit_platt(z: np.ndarray, y: np.ndarray, steps: int = 400) -> tuple[float, float]:
    """a·z + b by Newton steps on the log loss. Two parameters, no library."""
    a, b = 1.0, 0.0
    for _ in range(steps):
        p = sigmoid(a * z + b)
        w = np.clip(p * (1 - p), 1e-9, None)
        r = p - y
        g = np.array([np.dot(r, z), r.sum()])
        h = np.array([[np.dot(w * z, z), np.dot(w, z)], [np.dot(w, z), w.sum()]]) + 1e-6 * np.eye(2)
        step = np.linalg.solve(h, g)
        a, b = a - step[0], b - step[1]
        if np.max(np.abs(step)) < 1e-9:
            break
    return float(a), float(b)


def fit_isotonic(p: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Pool adjacent violators: the best monotone map from p to the outcome."""
    order = np.argsort(p, kind="mergesort")
    x, target = p[order], y[order].astype(np.float64)
    values = list(target)
    weights = [1.0] * len(values)
    i = 0
    while i < len(values) - 1:
        if values[i] <= values[i + 1] + 1e-12:
            i += 1
            continue
        total = weights[i] + weights[i + 1]
        values[i] = (values[i] * weights[i] + values[i + 1] * weights[i + 1]) / total
        weights[i] = total
        del values[i + 1], weights[i + 1]
        i = max(i - 1, 0)
    knots_x, knots_y = [], []
    at = 0
    for value, weight in zip(values, weights, strict=True):
        at += int(weight)
        knots_x.append(x[min(at - 1, len(x) - 1)])
        knots_y.append(value)
    return np.array(knots_x), np.array(knots_y)


def apply_isotonic(knots: tuple[np.ndarray, np.ndarray], p: np.ndarray) -> np.ndarray:
    x, y = knots
    return np.clip(np.interp(p, x, y), EPS, 1 - EPS)


def fit_stack(features: np.ndarray, y: np.ndarray, steps: int = 300) -> np.ndarray:
    """Logistic blend over several models' logits, with an intercept."""
    x = np.column_stack([features, np.ones(len(y))])
    w = np.zeros(x.shape[1])
    w[0] = 1.0
    for _ in range(steps):
        p = sigmoid(x @ w)
        g = x.T @ (p - y)
        s = np.clip(p * (1 - p), 1e-9, None)
        h = (x * s[:, None]).T @ x + 1e-6 * np.eye(x.shape[1])
        step = np.linalg.solve(h, g)
        w = w - step
        if np.max(np.abs(step)) < 1e-9:
            break
    return w


def row(name: str, y: np.ndarray, p: np.ndarray) -> dict:
    m = summarize(y, p).as_dict()
    return {"name": name, "auc": m["auc"], "log_loss": m["log_loss"], "ece": m["ece"]}


def stratified(y: np.ndarray, p: np.ndarray, seen: np.ndarray) -> list[dict]:
    out = []
    for label, lo, hi in (("first attempt", 0, 1), ("2nd–5th", 1, 5), ("6th+", 5, 10**9)):
        idx = (seen >= lo) & (seen < hi)
        if idx.sum() < 50:
            continue
        out.append(
            {
                "stratum": label,
                "events": int(idx.sum()),
                "base_rate": float(y[idx].mean()),
                "mean_p": float(p[idx].mean()),
                "log_loss": summarize(y[idx], p[idx]).as_dict()["log_loss"],
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--out")
    args = parser.parse_args()

    spec = yaml.safe_load(Path(args.dataset).read_text())
    ds = load_dataset(spec)
    train, val, test = split_by_student(ds, seed=args.seed)
    print(
        f"{ds.name} {ds.version}: {len(train.sequences)}/{len(val.sequences)}/{len(test.sequences)} learners"
    )

    from sabelia.training.trainer import TrainConfig
    from sabelia.training.trainer import train as fit

    result = fit(
        train,
        val,
        TrainConfig(model="sabelia", seed=args.seed, epochs=args.epochs, patience=5, log_every=10**6),
        log=lambda *_: None,
    )
    model = result.model
    shipped_t = model.temperature
    model.temperature = 1.0  # raw logits from here on; calibrators go on top

    y_val, p_val = predictions(model, val)
    y_test, p_test = predictions(model, test)
    z_val, z_test = logit(p_val), logit(p_test)

    bkt = BKT(em_iters=15).fit(train)
    pfa = PFA(epochs=30).fit(train)
    _, bkt_val = predictions(bkt, val)
    _, bkt_test = predictions(bkt, test)
    _, pfa_val = predictions(pfa, val)
    _, pfa_test = predictions(pfa, test)

    rows = [row("sabelia raw", y_test, p_test)]

    rows.append(row(f"temperature (shipped, T={shipped_t:.3f})", y_test, sigmoid(z_test / shipped_t)))

    a, b = fit_platt(z_val, y_val)
    rows.append(row(f"platt (a={a:.3f}, b={b:.3f})", y_test, sigmoid(a * z_test + b)))

    knots = fit_isotonic(p_val, y_val)
    rows.append(row("isotonic", y_test, apply_isotonic(knots, p_test)))

    w = fit_stack(np.column_stack([z_val, logit(bkt_val), logit(pfa_val)]), y_val)
    stacked = sigmoid(np.column_stack([z_test, logit(bkt_test), logit(pfa_test), np.ones(len(y_test))]) @ w)
    rows.append(row(f"stack sabelia+bkt+pfa (w={np.round(w, 3).tolist()})", y_test, stacked))

    rows.append(row("bkt alone", y_test, bkt_test))
    rows.append(row("pfa alone", y_test, pfa_test))

    print("\n| calibration | AUC | log loss | ECE |")
    print("|---|---|---|---|")
    for r in rows:
        print(f"| {r['name']} | {r['auc']:.4f} | {r['log_loss']:.4f} | {r['ece']:.4f} |")

    seen = prior_attempts(test)
    print("\nWhere the loss is (shipped temperature):")
    print("\n| stratum | events | base rate | mean p | log loss |")
    print("|---|---|---|---|---|")
    for s in stratified(y_test, sigmoid(z_test / shipped_t), seen):
        print(
            f"| {s['stratum']} | {s['events']} | {s['base_rate']:.3f} | "
            f"{s['mean_p']:.3f} | {s['log_loss']:.4f} |"
        )
    print("\nSame strata for BKT:")
    print("\n| stratum | events | base rate | mean p | log loss |")
    print("|---|---|---|---|---|")
    for s in stratified(y_test, bkt_test, seen):
        print(
            f"| {s['stratum']} | {s['events']} | {s['base_rate']:.3f} | "
            f"{s['mean_p']:.3f} | {s['log_loss']:.4f} |"
        )

    if args.out:
        Path(args.out).write_text(json.dumps({"rows": rows, "seed": args.seed}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
