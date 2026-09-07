"""The benchmark: every model, same split, same metrics, one table.

Runs (in this order, cheapest first): global mean, concept mean, the mastery
heuristic, PFA, BKT, the half-life forgetting model, DKT, and Aquilante with
its ablations. Each neural model is trained per seed with early stopping on
the validation split and evaluated once on the test split; metrics are the
mean over seeds with the standard deviation when there is more than one.
Every run is appended to ``runs.jsonl`` with dataset version, seed, config,
environment and git commit.

If a simple model wins, the table says so. That is the point of the table.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from aquilante.evaluation.metrics import summarize
from aquilante.experiments.registry import ExperimentRun, Registry
from aquilante.features.sequences import Dataset, split_by_student
from aquilante.memory.forgetting import HalfLifeModel
from aquilante.models.baselines import BKT, DAS3H, PFA, ConceptMean, GlobalMean, MasteryHeuristic

NEURAL = {
    "dkt": ("dkt", {}),
    "aquilante": ("aquilante", {}),
    "aquilante-no_time": ("aquilante", {"use_time": False, "use_forgetting": False}),
    "aquilante-no_forgetting": ("aquilante", {"use_forgetting": False}),
    "aquilante-no_response": ("aquilante", {"use_response": False}),
    "aquilante-no_item": ("aquilante", {"use_item": False}),
}


def run_benchmark(
    ds: Dataset,
    *,
    out: Path,
    seeds: int = 1,
    models: list[str] | None = None,
    epochs: int = 20,
    quick: bool = False,
) -> list[dict]:
    reg = Registry(out)
    rows: list[dict] = []
    per_model: dict[str, list[dict]] = {}

    def record(name: str, seed: int, metrics: dict, seconds: float, config: dict):
        reg.record(
            ExperimentRun(
                run_id=f"{name}-{ds.version}-s{seed}-{int(time.time())}",
                model=name,
                dataset=ds.name,
                dataset_version=ds.version,
                dataset_kind=ds.kind,
                seed=seed,
                config=config,
                metrics=metrics,
                train_seconds=seconds,
            )
        )
        per_model.setdefault(name, []).append({**metrics, "seconds": seconds})

    baselines = {
        "global_mean": lambda: GlobalMean(),
        "concept_mean": lambda: ConceptMean(),
        "mastery_heuristic": lambda: MasteryHeuristic(),
        "pfa": lambda: PFA(epochs=5 if quick else 30),
        "das3h": lambda: DAS3H(epochs=5 if quick else 30),
        "bkt": lambda: BKT(em_iters=3 if quick else 15),
        "half_life": lambda: HalfLifeModel(epochs=2 if quick else 8),
    }
    wanted = models or [*baselines, *NEURAL]

    for seed in range(seeds):
        train_ds, val_ds, test_ds = split_by_student(ds, seed=seed)
        for name, make in baselines.items():
            if name not in wanted:
                continue
            t0 = time.time()
            m = make()
            m.fit(train_ds) if name != "half_life" else m.fit(train_ds)
            y, p = _predict(m, test_ds)
            metrics = summarize(y, p).as_dict()
            record(name, seed, metrics, time.time() - t0, m.params())
        for name, (kind, mc) in NEURAL.items():
            if name not in wanted:
                continue
            try:
                from aquilante.training.trainer import TrainConfig, train  # noqa: PLC0415
            except ImportError:
                continue
            t0 = time.time()
            cfg = TrainConfig(
                model=kind,
                model_config=mc,
                seed=seed,
                epochs=3 if quick else epochs,
                patience=2 if quick else 5,
                log_every=10**6,
            )
            result = train(train_ds, val_ds, cfg, log=lambda *_: None)
            y, p = result.model.predict_dataset(test_ds)
            metrics = summarize(y, p).as_dict()
            metrics["best_epoch"] = result.best_epoch
            metrics["parameters"] = result.model.parameters_count()
            record(name, seed, metrics, time.time() - t0, cfg.to_dict())

    for name in wanted:
        runs = per_model.get(name, [])
        if not runs:
            continue
        row = {"model": name, "seeds": len(runs)}
        for k in ("auc", "log_loss", "brier", "ece", "accuracy"):
            vals = np.array([r[k] for r in runs], dtype=float)
            row[k] = float(vals.mean())
            if len(runs) > 1:
                row[f"{k}_sd"] = float(vals.std(ddof=1))
        row["seconds"] = float(np.mean([r["seconds"] for r in runs]))
        rows.append(row)
    rows.sort(key=lambda r: -r["auc"])
    return rows


def _predict(model, ds: Dataset):
    ys, ps = [], []
    for s in ds.sequences:
        ys.append(s.correct.astype(np.float64))
        ps.append(np.asarray(model.predict(s), dtype=np.float64))
    return np.concatenate(ys), np.concatenate(ps)
