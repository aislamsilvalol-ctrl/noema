#!/usr/bin/env python
"""Freeze Sabelia's benchmark runs into a JSON file the web app can render.

    python3 scripts/sabelia-snapshot.py

Reads every `sabelia/benchmarks/runs*/runs.jsonl`, aggregates the seeds of each
model on each dataset, and writes `apps/web/src/data/sabelia-benchmarks.json`.

The snapshot is the boundary. The product does not import the engine, does not
call it to draw a page, and does not depend on its virtualenv: the Lab reads a
file that was written when the benchmark ran, and the file says when. If the
snapshot is stale, the page says that too — a dated number is honest, a number
that pretends to be live is not.
"""

from __future__ import annotations

import json
import statistics
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNS = sorted((ROOT / "sabelia" / "benchmarks").glob("runs*/runs.jsonl"))
OUT = ROOT / "apps" / "web" / "src" / "data" / "sabelia-benchmarks.json"

METRICS = ("auc", "log_loss", "brier", "ece", "accuracy")


def main() -> int:
    by_dataset: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    latest: dict[str, dict[str, Any]] = {}
    for path in RUNS:
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            run = json.loads(line)
            key = f"{run['dataset']}:{run['dataset_version']}"
            # one row per (model, seed): a re-run of the same seed replaces it
            rows = by_dataset[key][run["model"]]
            rows[:] = [r for r in rows if r["seed"] != run["seed"]]
            rows.append(run)
            known = latest.get(key)
            if known is None or run["created_at"] > known["created_at"]:
                latest[key] = run

    datasets = []
    for key, models in by_dataset.items():
        head = latest[key]
        rows = []
        for model, runs in models.items():
            row: dict[str, Any] = {"model": model, "seeds": len(runs)}
            for metric in METRICS:
                values = [r["metrics"][metric] for r in runs]
                row[metric] = round(statistics.fmean(values), 4)
                if len(values) > 1:
                    row[f"{metric}_sd"] = round(statistics.stdev(values), 4)
            row["seconds"] = round(statistics.fmean([r["train_seconds"] for r in runs]))
            rows.append(row)
        rows.sort(key=lambda r: -r["auc"])
        datasets.append(
            {
                "dataset": head["dataset"],
                "version": head["dataset_version"],
                "kind": head["dataset_kind"],
                "ran_at": head["created_at"],
                "git": (head.get("git") or "")[:8],
                "models": rows,
            }
        )
    datasets.sort(key=lambda d: (d["kind"] != "public", -d["ran_at"]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {"generated_at": time.time(), "datasets": datasets}, indent=2, sort_keys=True
        )
        + "\n"
    )
    total = sum(len(d["models"]) for d in datasets)
    print(f"{len(datasets)} datasets, {total} model rows → {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
