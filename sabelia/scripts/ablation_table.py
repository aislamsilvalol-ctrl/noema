"""Ablations compared against the full model on the same seed, not on the mean.

.venv/bin/python scripts/ablation_table.py benchmarks/runs-ednet

The benchmark table reports each model's mean and the spread across seeds, and
on every dataset so far that spread has been wider than the gaps between the
Sabelia variants — which reads as "nothing can be concluded". That reading is
too pessimistic, because the variants share their seed: the same split, the
same initialisation, the same batch order. What varies between seeds is mostly
the dataset split, and it moves every variant together.

So this compares each ablation with the full model *within* a seed and reports
the differences: their mean, their spread, and how many seeds each way. A
difference whose spread straddles zero is undecided however many seeds there
are; one that is consistently negative across seeds means the removed part is
earning its place, even when both models sit inside each other's error bars in
the aggregate table.

This is a paired difference, not a significance test. Three seeds cannot carry
a p-value worth printing, and printing one would give the numbers an authority
they have not got.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

FULL = "sabelia"
METRIC = "auc"


def load(root: Path) -> dict[str, dict[str, dict[int, float]]]:
    """dataset → model → seed → metric, keeping the last run of each pair."""
    out: dict[str, dict[str, dict[int, float]]] = defaultdict(lambda: defaultdict(dict))
    for line in (root / "runs.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        run = json.loads(line)
        key = f"{run['dataset']} ({run['dataset_version']})"
        out[key][run["model"]][run["seed"]] = run["metrics"][METRIC]
    return out


def main(root: str) -> int:
    datasets = load(Path(root))
    for name, models in datasets.items():
        full = models.get(FULL)
        if not full:
            print(f"## {name}\n\nNo `{FULL}` run to compare against.\n")
            continue
        print(f"## {name}\n")
        print(f"Paired against `{FULL}` per seed. Negative means removing the part cost AUC.\n")
        print("| removed | seeds | Δ AUC (mean) | spread | per seed |")
        print("|---|---|---|---|---|")
        rows = []
        for model, by_seed in models.items():
            if not model.startswith(f"{FULL}-"):
                continue
            shared = sorted(set(by_seed) & set(full))
            if not shared:
                continue
            deltas = [by_seed[seed] - full[seed] for seed in shared]
            mean = statistics.fmean(deltas)
            spread = statistics.stdev(deltas) if len(deltas) > 1 else None
            rows.append((mean, model, shared, deltas, spread))
        for mean, model, shared, deltas, spread in sorted(rows):
            per_seed = " ".join(f"{d:+.4f}" for d in deltas)
            spread_text = f"± {spread:.4f}" if spread is not None else "—"
            print(
                f"| {model.removeprefix(FULL + '-')} | {len(shared)} | "
                f"{mean:+.4f} | {spread_text} | {per_seed} |"
            )
        if rows and len(rows[0][2]) > 1:
            decided = [
                (m, model)
                for m, model, _, deltas, _ in rows
                if all(d < 0 for d in deltas) or all(d > 0 for d in deltas)
            ]
            print()
            if decided:
                for mean, model in sorted(decided):
                    part = model.removeprefix(FULL + "-")
                    verdict = "costs" if mean < 0 else "gains"
                    print(f"- Removing **{part}** {verdict} AUC on every seed ({mean:+.4f} mean).")
            else:
                print("- No ablation moved the same way on every seed: all undecided.")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "benchmarks/runs"))
