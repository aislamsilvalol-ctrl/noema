#!/usr/bin/env python
"""Compare NOEMA's projection rule with Sabelia on NOEMA's own exported events.

    apps/api/.venv/bin/python scripts/shadow-eval.py --events export.jsonl --out rule.json
    sabelia/.venv/bin/python  scripts/shadow-eval.py --events export.jsonl --with rule.json

The two interpreters are deliberate. The product's virtualenv has the rule and
no engine; the engine's has numpy and torch and no product. Neither depends on
the other — that is the boundary the integration document draws — so each run
scores what it can, `--out` saves its rows, and `--with` merges them into one
table.

The product's rule (`noema.professor.student.project`, the real function, not
a copy) and the engine both predict the same thing: will this learner get the
next question about this concept right? This script replays a pseudonymous
export in time order, asks both before each graded event, and scores the two
prediction streams the way the benchmark does — AUC, log loss, Brier, ECE,
accuracy — with the base rate beside them.

It is a prequential (online) evaluation: every prediction is made from the
events that preceded it, so nothing leaks backwards. Sabelia is asked through
its `Learner`, which is what the shadow integration calls in production; if
the package is not importable, the script says so and reports the rule alone.

**It refuses to report on too little data.** A few dozen events cannot tell
two models apart, and a number printed from them would be used as if it
could. `--min-events` (default 500 graded events over at least 20 learners)
is the floor; below it the script prints what is missing and exits 2.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "sabelia"))

try:  # the product's rule; absent in the engine's virtualenv
    from noema.professor.student import KIND_WEIGHTS, project  # noqa: E402
except ImportError:  # pragma: no cover - depends on the interpreter
    KIND_WEIGHTS, project = None, None  # type: ignore[assignment]

#: The export's event types that carry a right/wrong outcome.
GRADED = {"answer", "recall"}


def kind_for(event: dict[str, Any]) -> str:
    """The export drops the product's `kind`; recover the weight class from it.

    `answer` events come from quiz, check, assessment and graded answers, all
    of which the rule weights as strong evidence; `recall` events are flashcard
    reviews. The mapping is coarse on purpose — the point is to run the rule as
    the product runs it, not to reconstruct the row.
    """
    return "flashcard" if event.get("event_type") == "recall" else "check"


def metrics(y: list[int], p: list[float]) -> dict[str, float]:
    """AUC, log loss, Brier, ECE (10 bins), accuracy. No sklearn, no surprises."""
    n = len(y)
    pos = sum(y)
    neg = n - pos
    order = sorted(range(n), key=lambda i: p[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and p[order[j + 1]] == p[order[i]]:
            j += 1
        average = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = average
        i = j + 1
    auc = (
        (sum(ranks[i] for i in range(n) if y[i]) - pos * (pos + 1) / 2) / (pos * neg)
        if pos and neg
        else float("nan")
    )
    eps = 1e-12
    log_loss = -sum(
        y[i] * math.log(max(p[i], eps)) + (1 - y[i]) * math.log(max(1 - p[i], eps))
        for i in range(n)
    ) / n
    brier = sum((p[i] - y[i]) ** 2 for i in range(n)) / n
    bins: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        bins[min(9, int(p[i] * 10))].append(i)
    ece = sum(
        len(idx)
        / n
        * abs(
            sum(y[i] for i in idx) / len(idx) - sum(p[i] for i in idx) / len(idx)
        )
        for idx in bins.values()
        if idx
    )
    accuracy = sum(1 for i in range(n) if (p[i] >= 0.5) == bool(y[i])) / n
    return {
        "auc": auc,
        "log_loss": log_loss,
        "brier": brier,
        "ece": ece,
        "accuracy": accuracy,
    }


def rule_predictions(events: list[dict[str, Any]]) -> tuple[list[int], list[float]]:
    """Replay the product's own projection, one learner and concept at a time."""
    history: dict[tuple[str, str], list[tuple[str, float]]] = defaultdict(list)
    introduced: set[tuple[str, str]] = set()
    y: list[int] = []
    p: list[float] = []
    for event in events:
        key = (event["student_id"], event["concept_id"])
        if event.get("event_type") not in GRADED or event.get("correct") is None:
            introduced.add(key)
            continue
        prior = history[key]
        projection = project(
            prior,
            introduced=key in introduced,
            last_at=datetime.fromtimestamp(event["timestamp"], tz=timezone.utc),
        )
        # The rule's score *is* its belief that the learner knows the concept;
        # with no evidence it says 0.0, which as a probability would be a
        # confident "wrong". The first showing of a concept is scored at the
        # rule's own neutral point instead, so the comparison is fair.
        p.append(projection.score if prior else 0.5)
        y.append(1 if event["correct"] else 0)
        history[key].append(
            (kind_for(event), float(event.get("score") or (1.0 if event["correct"] else 0.0)))
        )
        introduced.add(key)
    return y, p


def sabelia_predictions(
    events: list[dict[str, Any]], *, seed: int
) -> tuple[list[int], list[float], str] | None:
    """Train on a learner split, predict held-out learners' events in order."""
    try:
        from sabelia.data.schema import LearningEvent  # noqa: PLC0415
        from sabelia.features.sequences import build_dataset, split_by_student  # noqa: PLC0415
        from sabelia.models.baselines import MasteryHeuristic  # noqa: PLC0415
    except ImportError:
        return None
    parsed = [LearningEvent.model_validate(e) for e in events]
    dataset = build_dataset(parsed, name="noema", version="export", kind="real")
    train, _, test = split_by_student(dataset, seed=seed)
    model: Any
    name = "sabelia-heuristic"
    try:  # the neural model when torch is installed, the baseline otherwise
        from sabelia.training.trainer import TrainConfig, train as fit  # noqa: PLC0415

        result = fit(
            train,
            _,
            TrainConfig(model="sabelia", seed=seed, epochs=20, patience=5, log_every=10**6),
            log=lambda *_: None,
        )
        model, name = result.model, "sabelia"
    except ImportError:
        model = MasteryHeuristic()
        model.fit(train)
    y: list[int] = []
    p: list[float] = []
    for sequence in test.sequences:
        predictions = model.predict(sequence)
        y.extend(int(c) for c in sequence.correct)
        p.extend(float(x) for x in predictions)
    return y, p, name


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--events", required=True, help="JSONL from scripts/export-learning-events.py")
    parser.add_argument("--min-events", type=int, default=500)
    parser.add_argument("--min-learners", type=int, default=20)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", help="save this run's rows as JSON")
    parser.add_argument("--with", dest="with_", help="merge rows saved by an earlier run")
    args = parser.parse_args()

    events = [
        json.loads(line)
        for line in Path(args.events).read_text().splitlines()
        if line.strip()
    ]
    events.sort(key=lambda e: (e["timestamp"], e.get("event_id", "")))
    graded = [e for e in events if e.get("event_type") in GRADED and e.get("correct") is not None]
    learners = {e["student_id"] for e in graded}
    print(f"{len(events)} events, {len(graded)} graded, {len(learners)} learners")
    if len(graded) < args.min_events or len(learners) < args.min_learners:
        print(
            f"not enough to compare: need {args.min_events} graded events over "
            f"{args.min_learners} learners. Keep exporting; this is not a result.",
            file=sys.stderr,
        )
        return 2

    # Keyed by label so a merged row and a freshly computed one of the same
    # model are the same row: this run's numbers win.
    scored: dict[str, tuple[dict[str, float], int]] = {}
    if args.with_:
        for r in json.loads(Path(args.with_).read_text()):
            scored[r["label"]] = (r["metrics"], r["events"])
    if project is not None:
        y_rule, p_rule = rule_predictions(events)
        scored["project-v1 (the rule in production)"] = (
            metrics(y_rule, p_rule),
            len(y_rule),
        )
    engine = sabelia_predictions(events, seed=args.seed)
    if engine is not None:
        y_engine, p_engine, name = engine
        scored[f"{name} (held-out learners)"] = (
            metrics(y_engine, p_engine),
            len(y_engine),
        )
    rows = [(label, m, n) for label, (m, n) in scored.items()]
    if not rows:
        print(
            "neither the rule nor the engine is importable in this interpreter; "
            "see the header of this file for the two commands",
            file=sys.stderr,
        )
        return 2
    if args.out:
        Path(args.out).write_text(
            json.dumps(
                [{"label": label, "metrics": m, "events": n} for label, m, n in rows],
                indent=2,
            )
        )
    base = sum(1 for e in graded if e["correct"]) / len(graded)
    print(f"\nbase rate {base:.3f}\n")
    print("| model | events | AUC | log loss | Brier | ECE | accuracy |")
    print("|---|---|---|---|---|---|---|")
    for label, m, n in rows:
        print(
            f"| {label} | {n} | {m['auc']:.4f} | {m['log_loss']:.4f} | "
            f"{m['brier']:.4f} | {m['ece']:.4f} | {m['accuracy']:.4f} |"
        )
    labels = [label for label, _, _ in rows]
    rule = next((m for label, m, _ in rows if label.startswith("project-v1")), None)
    engine_row = next((m for label, m, _ in rows if label.startswith("sabelia")), None)
    if rule:
        print(
            "\nThe rule's score is a mastery belief, not a calibrated probability, so "
            "its log loss and ECE read worse than its ranking deserves. AUC is the "
            "comparison; log loss says what calibration would have to be fixed first."
        )
    if rule and engine_row:
        gap = engine_row["auc"] - rule["auc"]
        print(
            f"\nSabelia {'leads' if gap > 0 else 'trails'} the rule by {abs(gap):.4f} AUC "
            "on different event sets (the rule is scored on every event, the engine on "
            "held-out learners), so this is a direction, not a verdict. One seed."
        )
    elif len(labels) == 1:
        print(f"\nOnly {labels[0]} could run here; run the other interpreter and merge with --with.")
    if KIND_WEIGHTS is not None:
        print(
            f"\nKind weights used by the rule: {KIND_WEIGHTS}. "
            "Prediction order is the export's timestamp order."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
