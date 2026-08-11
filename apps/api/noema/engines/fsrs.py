"""FSRS scheduler — pure functions over immutable state.

Implements the DSR model (difficulty, stability, retrievability) described in
``docs/fsrs.md``. Deliberately free of I/O and of any ambient clock: elapsed time is
an argument. That is what allows the whole review history of a user to be replayed
offline when the weights change.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum
from typing import Final

__all__ = [
    "DEFAULT_WEIGHTS",
    "MemoryState",
    "Rating",
    "Weights",
    "interval_days",
    "next_state",
    "retrievability",
]

DECAY: Final = -0.5
FACTOR: Final = 19 / 81

MIN_DIFFICULTY: Final = 1.0
MAX_DIFFICULTY: Final = 10.0
MIN_STABILITY: Final = 0.01


class Rating(IntEnum):
    AGAIN = 1
    HARD = 2
    GOOD = 3
    EASY = 4


Weights = tuple[float, ...]

#: Published FSRS-4.5 defaults. Every user starts here; personal weights are fitted
#: from their own review log once they cross ``NOEMA_FSRS_OPTIMIZE_MIN_REVIEWS``.
DEFAULT_WEIGHTS: Final[Weights] = (
    0.4872,
    1.4003,
    3.7145,
    13.8206,  # w0-w3  initial stability per rating
    5.1618,
    1.2298,  # w4-w5  initial difficulty
    0.8975,
    0.0310,  # w6-w7  difficulty update + mean reversion
    1.6474,
    0.1367,
    1.0461,  # w8-w10 stability growth on success
    2.1072,
    0.0793,
    0.3246,
    1.5870,  # w11-w14 post-lapse stability
    0.2272,
    2.8755,  # w15-w16 hard penalty, easy bonus
)


@dataclass(frozen=True, slots=True)
class MemoryState:
    """Memory state of a single card. ``stability`` is in days."""

    stability: float
    difficulty: float

    def __post_init__(self) -> None:
        if self.stability < MIN_STABILITY:
            raise ValueError(
                f"stability must be >= {MIN_STABILITY}, got {self.stability}"
            )
        if not MIN_DIFFICULTY <= self.difficulty <= MAX_DIFFICULTY:
            raise ValueError(f"difficulty out of range: {self.difficulty}")


def retrievability(state: MemoryState, elapsed_days: float) -> float:
    """Probability of recall after ``elapsed_days`` since the last review.

    The power forgetting curve of FSRS-4.5, which fits observed review data better
    than the exponential curve used by SM-2 derivatives.
    """
    if elapsed_days < 0:
        raise ValueError("elapsed_days must be non-negative")
    return float((1 + FACTOR * elapsed_days / state.stability) ** DECAY)


def interval_days(state: MemoryState, target_retention: float) -> float:
    """Days until retrievability decays to ``target_retention``."""
    if not 0 < target_retention < 1:
        raise ValueError("target_retention must be in (0, 1)")
    return float(state.stability / FACTOR * (target_retention ** (1 / DECAY) - 1))


def next_state(
    state: MemoryState | None,
    rating: Rating,
    elapsed_days: float,
    w: Weights = DEFAULT_WEIGHTS,
) -> MemoryState:
    """Memory state after a review.

    ``state`` is ``None`` for a card's first review; ``elapsed_days`` is ignored in
    that case.
    """
    if state is None:
        return MemoryState(
            stability=max(w[rating - 1], MIN_STABILITY),
            difficulty=_clamp_difficulty(_initial_difficulty(rating, w)),
        )

    r = retrievability(state, elapsed_days)
    difficulty = _clamp_difficulty(_next_difficulty(state.difficulty, rating, w))
    stability = (
        _stability_after_lapse(state, r, w)
        if rating is Rating.AGAIN
        else _stability_after_success(state, r, rating, w)
    )
    return MemoryState(stability=max(stability, MIN_STABILITY), difficulty=difficulty)


def _initial_difficulty(rating: Rating, w: Weights) -> float:
    return w[4] - math.exp(w[5] * (rating - 1)) + 1


def _next_difficulty(difficulty: float, rating: Rating, w: Weights) -> float:
    # Mean reversion toward the difficulty an "Easy" first answer would imply.
    # Without it, difficulty ratchets upward forever and cards never recover.
    delta = difficulty - w[6] * (rating - 3)
    return w[7] * _initial_difficulty(Rating.EASY, w) + (1 - w[7]) * delta


def _stability_after_success(
    state: MemoryState, r: float, rating: Rating, w: Weights
) -> float:
    hard_penalty = w[15] if rating is Rating.HARD else 1.0
    easy_bonus = w[16] if rating is Rating.EASY else 1.0
    growth = (
        math.exp(w[8])
        * (11 - state.difficulty)
        * math.pow(state.stability, -w[9])
        * (math.exp(w[10] * (1 - r)) - 1)
        * hard_penalty
        * easy_bonus
    )
    return state.stability * (1 + growth)


def _stability_after_lapse(state: MemoryState, r: float, w: Weights) -> float:
    recovered = (
        w[11]
        * math.pow(state.difficulty, -w[12])
        * (math.pow(state.stability + 1, w[13]) - 1)
        * math.exp(w[14] * (1 - r))
    )
    # A lapse never increases stability, whatever the weights say.
    return min(recovered, state.stability)


def _clamp_difficulty(value: float) -> float:
    return min(max(value, MIN_DIFFICULTY), MAX_DIFFICULTY)
