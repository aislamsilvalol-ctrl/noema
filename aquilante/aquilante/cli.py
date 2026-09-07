"""``aquilante`` command line: simulate, benchmark, train, evaluate, compare, serve.

    aquilante simulate --students 300 --out data/synthetic.jsonl
    aquilante benchmark --dataset configs/datasets/synthetic.yaml --out runs/
    aquilante train --dataset configs/datasets/synthetic.yaml \\
        --config configs/train/aquilante.yaml --out runs/
    aquilante compare --runs runs/
    aquilante serve --model runs/models/aquilante/<version>

Everything the commands do is a function in the library; the CLI only parses.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import yaml

from aquilante.data.adapters import load_dataset, write_jsonl
from aquilante.evaluation.metrics import reliability_table, summarize
from aquilante.experiments.registry import ExperimentRun, Registry
from aquilante.features.sequences import split_by_student
from aquilante.simulation.simulator import SimulatorConfig, simulate


def _dataset_from_arg(arg: str):
    p = Path(arg)
    spec = yaml.safe_load(p.read_text()) if p.suffix in (".yaml", ".yml") else json.loads(arg)
    return load_dataset(spec), spec


def cmd_simulate(a: argparse.Namespace) -> int:
    cfg = SimulatorConfig(students=a.students, seed=a.seed, events_per_student=a.events)
    n = write_jsonl(simulate(cfg), Path(a.out))
    print(f"wrote {n} events to {a.out}")
    return 0


def cmd_describe(a: argparse.Namespace) -> int:
    ds, _ = _dataset_from_arg(a.dataset)
    print(json.dumps(ds.describe(), indent=2))
    return 0


def cmd_benchmark(a: argparse.Namespace) -> int:
    from aquilante.benchmarks import run_benchmark  # noqa: PLC0415

    ds, spec = _dataset_from_arg(a.dataset)
    rows = run_benchmark(
        ds,
        out=Path(a.out),
        seeds=a.seeds,
        models=a.models.split(",") if a.models else None,
        epochs=a.epochs,
        quick=a.quick,
    )
    print(_table(rows))
    return 0


def cmd_train(a: argparse.Namespace) -> int:
    from aquilante.training.trainer import TrainConfig, save_checkpoint, train  # noqa: PLC0415

    ds, spec = _dataset_from_arg(a.dataset)
    cfg = TrainConfig.from_yaml(Path(a.config))
    if a.seed is not None:
        cfg.seed = a.seed
    train_ds, val_ds, test_ds = split_by_student(ds, seed=cfg.seed)
    result = train(train_ds, val_ds, cfg)
    y, p = result.model.predict_dataset(test_ds)
    test = summarize(y, p)
    reg = Registry(Path(a.out))
    version = time.strftime("%Y%m%d-%H%M%S") + f"-s{cfg.seed}"
    model_dir = reg.register(
        cfg.model,
        version,
        payload={
            "config": cfg.to_dict(),
            "vocab_size": {"concepts": ds.vocab.n_concepts, "items": ds.vocab.n_items},
            "dataset": ds.describe(),
        },
        metrics={"val": result.val_metrics, "test": test.as_dict()},
    )
    save_checkpoint(result.model, model_dir / "weights.pt")
    (model_dir / "vocab.json").write_text(json.dumps(ds.vocab.to_dict()))
    (model_dir / "history.json").write_text(json.dumps(result.history, indent=2))
    (model_dir / "reliability.json").write_text(json.dumps(reliability_table(y, p), indent=2))
    reg.record(
        ExperimentRun(
            run_id=version,
            model=cfg.model,
            dataset=ds.name,
            dataset_version=ds.version,
            dataset_kind=ds.kind,
            seed=cfg.seed,
            config=cfg.to_dict(),
            metrics={"val": result.val_metrics, "test": test.as_dict()},
            train_seconds=result.seconds,
        )
    )
    print(
        json.dumps(
            {
                "model_dir": str(model_dir),
                "test": test.as_dict(),
                "seconds": round(result.seconds, 1),
            },
            indent=2,
        )
    )
    return 0


def cmd_compare(a: argparse.Namespace) -> int:
    reg = Registry(Path(a.runs))
    rows = reg.compare(a.dataset, metric=a.metric)
    flat = [
        {
            "model": r["model"],
            "dataset": r["dataset"],
            "kind": r["dataset_kind"],
            "seed": r["seed"],
            **{
                k: v
                for k, v in (r["metrics"].get("test") or r["metrics"]).items()
                if isinstance(v, (int, float))
            },
        }
        for r in rows
    ]
    print(_table(flat))
    return 0


def cmd_serve(a: argparse.Namespace) -> int:
    import uvicorn  # noqa: PLC0415

    from aquilante.inference.service import create_app  # noqa: PLC0415

    uvicorn.run(create_app(model_dir=Path(a.model) if a.model else None), host=a.host, port=a.port)
    return 0


def _table(rows: list[dict]) -> str:
    if not rows:
        return "(no rows)"
    cols = list(rows[0].keys())
    widths = {c: max(len(str(c)), *(len(_fmt(r.get(c))) for r in rows)) for c in cols}
    line = " | ".join(str(c).ljust(widths[c]) for c in cols)
    sep = "-+-".join("-" * widths[c] for c in cols)
    body = "\n".join(" | ".join(_fmt(r.get(c)).ljust(widths[c]) for c in cols) for r in rows)
    return f"{line}\n{sep}\n{body}"


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.4f}"
    return "" if v is None else str(v)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="aquilante", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("simulate", help="write synthetic learning events as JSONL")
    s.add_argument("--students", type=int, default=200)
    s.add_argument("--events", type=int, default=120)
    s.add_argument("--seed", type=int, default=7)
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_simulate)

    d = sub.add_parser("describe", help="summarise a dataset spec")
    d.add_argument("--dataset", required=True)
    d.set_defaults(fn=cmd_describe)

    b = sub.add_parser("benchmark", help="baselines vs neural models on one dataset")
    b.add_argument("--dataset", required=True)
    b.add_argument("--out", default="runs")
    b.add_argument("--seeds", type=int, default=1)
    b.add_argument("--models", default=None, help="comma list; default all")
    b.add_argument("--epochs", type=int, default=20)
    b.add_argument("--quick", action="store_true", help="fewer epochs and EM iterations, for smoke tests")
    b.set_defaults(fn=cmd_benchmark)

    t = sub.add_parser("train", help="train one neural model from a YAML config and register it")
    t.add_argument("--dataset", required=True)
    t.add_argument("--config", required=True)
    t.add_argument("--seed", type=int, default=None)
    t.add_argument("--out", default="runs")
    t.set_defaults(fn=cmd_train)

    c = sub.add_parser("compare", help="rank recorded runs")
    c.add_argument("--runs", default="runs")
    c.add_argument("--dataset", default=None)
    c.add_argument("--metric", default="auc")
    c.set_defaults(fn=cmd_compare)

    v = sub.add_parser("serve", help="run the inference service")
    v.add_argument(
        "--model", default=None, help="registered model directory; without it the heuristic serves"
    )
    v.add_argument("--host", default="127.0.0.1")
    v.add_argument("--port", type=int, default=8020)
    v.set_defaults(fn=cmd_serve)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
