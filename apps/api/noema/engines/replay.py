"""Replaying a review history to find out whether the scheduler was right.

The evidence log is append-only precisely so this is possible: every review records
the state it started from and the state it produced, which means the whole history
can be re-run under a different set of FSRS weights or a different target retention
and the outcomes compared.

Without this, `docs/fsrs.md` and `docs/learning-engine.md` are full of constants
nobody can evaluate — and a change to any of them is an opinion.

Pure functions. No database, no clock.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final

from noema.engines import fsrs

__all__ = [
    "Attempt",
    "Calibration",
    "ReplayResult",
    "compare",
    "replay",
]

#: Buckets for the reliability curve. Ten is enough to see a systematic bias and few
#: enough that each bucket holds data on a realistic history.
BUCKETS: Final = 10

#: A rating above Again means the learner recalled it. That is the event the
#: forgetting curve claims to predict.
RECALLED_FROM: Final = 2


@dataclass(frozen=True, slots=True)
class Attempt:
    """One review, as the log recorded it."""

    card_id: str
    elapsed_days: float
    rating: fsrs.Rating

    @property
    def recalled(self) -> bool:
        return int(self.rating) >= RECALLED_FROM


@dataclass(frozen=True, slots=True)
class Calibration:
    """How well predicted recall matched what happened."""

    predicted: float
    actual: float
    count: int

    @property
    def error(self) -> float:
        """Positive means the model was optimistic about the learner."""
        return self.predicted - self.actual


@dataclass(frozen=True, slots=True)
class ReplayResult:
    attempts: int
    mean_predicted: float
    actual_recall: float
    log_loss: float
    #: Mean absolute error across buckets, weighted by how much data each holds.
    calibration_error: float
    buckets: list[Calibration] = field(default_factory=list)

    @property
    def optimistic(self) -> bool:
        """The model expected more recall than the learner delivered."""
        return self.mean_predicted > self.actual_recall

    def summary(self) -> str:
        # No history means no claim. With nothing to score, predicted and actual
        # are both zero, the gap is zero, and the sentence below would announce
        # "well calibrated over 0 reviews" — a confident number from no evidence,
        # which is the one thing this whole module exists to catch. It is shown
        # on the progress screen whether or not the result is marked reliable, so
        # a new learner read it as a claim about their own history.
        if self.attempts == 0:
            return "No reviews scored yet, so there is nothing to judge."

        direction = "optimistic" if self.optimistic else "pessimistic"
        gap = abs(self.mean_predicted - self.actual_recall)
        if gap < 0.02:
            return f"Well calibrated over {self.attempts} reviews."
        return (
            f"{direction.capitalize()} by {gap:.0%} over {self.attempts} reviews: "
            f"predicted {self.mean_predicted:.0%} recall, saw {self.actual_recall:.0%}."
        )


def replay(
    attempts: Sequence[Attempt],
    *,
    weights: fsrs.Weights = fsrs.DEFAULT_WEIGHTS,
) -> ReplayResult:
    """Re-run a history and score the predictions it would have made.

    Each attempt is predicted *before* it is applied, so the model is never scored
    on information it would not have had.
    """
    states: dict[str, fsrs.MemoryState] = {}
    predictions: list[float] = []
    outcomes: list[bool] = []

    for attempt in attempts:
        state = states.get(attempt.card_id)

        if state is not None:
            predictions.append(fsrs.retrievability(state, attempt.elapsed_days))
            outcomes.append(attempt.recalled)

        # A first exposure has no prediction to score — there was no memory yet.
        states[attempt.card_id] = fsrs.next_state(
            state, attempt.rating, attempt.elapsed_days, weights
        )

    if not predictions:
        return ReplayResult(0, 0.0, 0.0, 0.0, 0.0, [])

    buckets = _buckets(predictions, outcomes)
    return ReplayResult(
        attempts=len(predictions),
        mean_predicted=sum(predictions) / len(predictions),
        actual_recall=sum(outcomes) / len(outcomes),
        log_loss=_log_loss(predictions, outcomes),
        calibration_error=_weighted_error(buckets, len(predictions)),
        buckets=buckets,
    )


def compare(
    attempts: Sequence[Attempt],
    *,
    candidate: fsrs.Weights,
    baseline: fsrs.Weights = fsrs.DEFAULT_WEIGHTS,
) -> tuple[ReplayResult, ReplayResult, bool]:
    """Score two weight sets on the same history.

    Returns ``(baseline, candidate, candidate_is_better)``. Better means lower log
    loss — the model assigned higher probability to what actually happened. Mean
    accuracy alone would reward a model that says 90% to everything.
    """
    before = replay(attempts, weights=baseline)
    after = replay(attempts, weights=candidate)
    return before, after, after.log_loss < before.log_loss


def _buckets(predictions: Sequence[float], outcomes: Sequence[bool]) -> list[Calibration]:
    """The reliability curve: within each predicted band, what actually happened."""
    grouped: dict[int, list[tuple[float, bool]]] = {}

    for predicted, outcome in zip(predictions, outcomes, strict=True):
        index = min(int(predicted * BUCKETS), BUCKETS - 1)
        grouped.setdefault(index, []).append((predicted, outcome))

    return [
        Calibration(
            predicted=sum(p for p, _ in rows) / len(rows),
            actual=sum(1 for _, o in rows if o) / len(rows),
            count=len(rows),
        )
        for _, rows in sorted(grouped.items())
    ]


def _log_loss(predictions: Sequence[float], outcomes: Sequence[bool]) -> float:
    """Penalises confident wrong predictions much harder than uncertain ones.

    This is the quantity the FSRS optimiser minimises, so using it here means a
    weight change is judged by the same measure that produced it.
    """
    epsilon = 1e-9
    total = 0.0
    for predicted, outcome in zip(predictions, outcomes, strict=True):
        clamped = min(max(predicted, epsilon), 1 - epsilon)
        total -= math.log(clamped) if outcome else math.log(1 - clamped)
    return total / len(predictions)


def _weighted_error(buckets: Sequence[Calibration], total: int) -> float:
    if not buckets or total == 0:
        return 0.0
    return sum(abs(b.error) * b.count for b in buckets) / total
