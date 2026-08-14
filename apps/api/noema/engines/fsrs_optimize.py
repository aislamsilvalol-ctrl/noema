"""Fitting FSRS to one learner instead of to everyone.

The default weights were fitted on a large public dataset. They are a good prior
and they are not *you*: someone who reviews at 6am after bad sleep, or who rates
Hard when they mean Good, decays differently from the average of a hundred
thousand strangers.

Two things make this an experiment rather than a flourish:

**The split is chronological.** Fit on the earlier reviews, judge on the later
ones. A random split leaks the future into the past — the same card appears on
both sides — and every parameter set looks brilliant.

**It has to win by a margin, on data it never saw.** Search hard enough and
something will beat the baseline on the training half by a hair. Adopting that is
how a system convinces itself it has learned something about a learner when it has
learned something about noise.

Pure: attempts in, a verdict out. No database, no clock.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from noema.engines import fsrs
from noema.engines.replay import Attempt, replay

__all__ = ["Fit", "optimise"]

#: Fraction of the history used to fit. The rest is never seen during the search.
TRAIN_SPLIT = 0.8

#: How much better the candidate must be on the held-out half, in log loss. Small
#: enough that a real improvement counts, large enough that noise does not.
MARGIN = 0.005

#: The weights worth moving, and how far. Not all seventeen: the initial-stability
#: and difficulty terms carry most of the per-learner variation, and searching the
#: whole vector on a few hundred reviews fits noise with great enthusiasm.
BOUNDS: dict[int, tuple[float, float]] = {
    0: (0.1, 2.0),  # initial stability, Again
    1: (0.5, 4.0),  # initial stability, Hard
    2: (1.0, 10.0),  # initial stability, Good
    3: (5.0, 25.0),  # initial stability, Easy
    4: (3.0, 9.0),  # initial difficulty
    5: (0.2, 1.5),  # difficulty spread across ratings
    6: (0.5, 2.5),  # difficulty change per rating
}

#: Multipliers tried per weight, per round. Coordinate search rather than gradient
#: descent: seventeen dimensions of noisy data do not deserve a gradient, and this
#: is inspectable by anyone reading it.
STEPS = (0.8, 0.9, 1.1, 1.25)

ROUNDS = 3


@dataclass(frozen=True, slots=True)
class Fit:
    weights: fsrs.Weights
    adopted: bool
    #: Log loss on the held-out half, for the baseline and the candidate.
    baseline_loss: float
    candidate_loss: float
    train_attempts: int
    validation_attempts: int
    summary: str


def optimise(
    attempts: Sequence[Attempt],
    *,
    baseline: fsrs.Weights = fsrs.DEFAULT_WEIGHTS,
    min_reviews: int = 400,
) -> Fit:
    """Search for weights that predict this learner better than the defaults."""
    total = len(attempts)
    if total < min_reviews:
        return Fit(
            weights=baseline,
            adopted=False,
            baseline_loss=0.0,
            candidate_loss=0.0,
            train_attempts=total,
            validation_attempts=0,
            summary=(
                f"{total} reviews so far. Fitting starts at {min_reviews}, because "
                "below that the search finds your noise rather than your memory."
            ),
        )

    cut = int(total * TRAIN_SPLIT)
    train, validation = list(attempts[:cut]), list(attempts[cut:])

    candidate = _search(train, baseline)

    base_loss = replay(validation, weights=baseline).log_loss
    new_loss = replay(validation, weights=candidate).log_loss
    improvement = base_loss - new_loss
    adopted = improvement >= MARGIN

    return Fit(
        weights=candidate if adopted else baseline,
        adopted=adopted,
        baseline_loss=round(base_loss, 4),
        candidate_loss=round(new_loss, 4),
        train_attempts=len(train),
        validation_attempts=len(validation),
        summary=(
            f"Fitted on {len(train)} reviews and checked against {len(validation)} "
            f"it never saw: log loss {base_loss:.3f} → {new_loss:.3f}. "
            + (
                "Your schedule now uses parameters fitted to you."
                if adopted
                else "Not enough of an improvement to be worth trusting, so the "
                "defaults stay."
            )
        ),
    )


def _search(train: Sequence[Attempt], baseline: fsrs.Weights) -> fsrs.Weights:
    """Coordinate search: try each weight in turn, keep what helps."""
    best = list(baseline)
    best_loss = replay(train, weights=tuple(best)).log_loss

    for _ in range(ROUNDS):
        improved = False

        for index, (low, high) in BOUNDS.items():
            if index >= len(best):
                continue

            for step in STEPS:
                trial = list(best)
                trial[index] = min(max(best[index] * step, low), high)
                if trial[index] == best[index]:
                    continue

                loss = replay(train, weights=tuple(trial)).log_loss
                if loss < best_loss:
                    best, best_loss, improved = trial, loss, True

        # Another round only helps if the last one moved something.
        if not improved:
            break

    return tuple(best)
