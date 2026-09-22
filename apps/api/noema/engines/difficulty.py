"""Item difficulty from what learners showed, not only what an author declared.

An author calls an item "hard" before anyone has answered it. Once people have,
the wrong-answer rate is a better reading — but a raw rate is a bad one for the
first few answers: one wrong answer out of one is a rate of 1.0, and the item
would swing from "easy" to "expert" and back with every attempt. So the rate is
smoothed towards a prior, the declared difficulty, with the weight of a handful
of pseudo-answers. Two real answers barely move it; twenty own it.

Pure: integers and floats in, a float out.
"""

from __future__ import annotations

__all__ = [
    "MIN_OBSERVATIONS",
    "PRIOR_WEIGHT",
    "item_difficulty",
    "smoothed_difficulty",
]

#: How many pseudo-answers the declared difficulty is worth. At five, a single
#: wrong answer on a "medium" (0.5) item reads 0.58 rather than 1.0, and it
#: takes roughly ten real answers for the data to outweigh the author.
PRIOR_WEIGHT = 5.0

#: Below this many real answers the observed value is still mostly the prior
#: dressed up, so the mastery engine keeps using the declared weight and nothing
#: changes for an item nobody has studied much. At ten, with `PRIOR_WEIGHT` of
#: five, two thirds of the number is data.
MIN_OBSERVATIONS = 10


def smoothed_difficulty(wrong: int, total: int, *, prior: float) -> float:
    """The wrong-answer rate, pulled towards ``prior`` by ``PRIOR_WEIGHT`` pseudo-answers.

    ``(wrong + PRIOR_WEIGHT * prior) / (total + PRIOR_WEIGHT)``. With no answers
    at all it is exactly the prior; with many, it is the raw rate.
    """
    if not 0.0 <= prior <= 1.0:
        raise ValueError(f"prior must be in [0, 1], got {prior}")
    if total < 0 or wrong < 0 or wrong > total:
        raise ValueError(f"need 0 <= wrong <= total, got wrong={wrong} total={total}")
    return (wrong + PRIOR_WEIGHT * prior) / (total + PRIOR_WEIGHT)


def item_difficulty(declared: float, observed: float | None, count: int | None) -> float:
    """The difficulty the mastery engine should weight an item by.

    The observed value when at least ``MIN_OBSERVATIONS`` answers stand behind it,
    the declared one otherwise — so an item with thin evidence behaves exactly as
    it did before anything was observed.
    """
    if observed is None or count is None or count < MIN_OBSERVATIONS:
        return declared
    return min(max(observed, 0.0), 1.0)
