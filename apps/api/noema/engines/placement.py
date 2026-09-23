"""Choosing the question that tells us most, and knowing when to stop.

A placement test that asks everyone the same twenty questions wastes the time of
the learner who already knows the material and learns little about the one who
does not. The useful question is the one whose answer is hardest to predict: at
the point where someone has an even chance, the answer carries a full bit; where
they are nearly certain to be right, it carries almost nothing.

This is the Rasch reading of that idea. One ability per learner on a logit
scale, one difficulty per item on the same scale, and the chance of a correct
answer is the logistic of their difference. Item information is ``p(1-p)``,
largest where the two meet — so the next question is the one whose difficulty
sits closest to what we currently believe the ability to be, and the belief is
updated after every answer.

**Deliberately not a full IRT implementation.** No discrimination parameter, no
guessing parameter, no marginal maximum likelihood. Those need a calibrated item
bank and thousands of responses to estimate, and this has to work on the first
session of a product that has neither. The one-parameter model degrades
honestly: with a bad difficulty estimate it still asks something reasonable and
still converges, just more slowly. See `docs/learning-engine.md` §14-§16.

Difficulty arrives as the product's 0-1 scale — the share of learners who get
the item wrong, calibrated in `engines.difficulty` — and is converted here. That
is the same number the mastery engine weights evidence by, so a diagnostic and a
review are reading one scale, not two.

Pure: floats in, floats out. No session, no clock, no I/O.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = [
    "MAX_QUESTIONS",
    "MIN_QUESTIONS",
    "PRIOR_SD",
    "STOP_SE",
    "Ability",
    "difficulty_logit",
    "information",
    "next_item",
    "probability_correct",
    "should_stop",
    "update",
]

#: What we believe before anyone answers anything: an average learner, held
#: loosely. Wide enough that three answers can move it a long way, which is
#: the point of asking.
PRIOR_MEAN = 0.0
PRIOR_SD = 1.5

#: Stop once the posterior is this tight.
#:
#: The number is bounded by arithmetic, not taste. An answer contributes at most
#: ``p(1-p) = 0.25`` to precision, and only when the item sits exactly at the
#: learner's ability; the prior contributes ``1/PRIOR_SD**2 = 0.44``. So after
#: ``n`` perfectly chosen questions the standard error cannot fall below
#: ``1/sqrt(0.44 + 0.25n)`` — 0.92 at three questions, 0.68 at seven, 0.64 at
#: eight. A threshold under 0.64 could therefore never fire inside `MAX_QUESTIONS`,
#: and an early-stopping rule that cannot fire is a lie told in a constant.
#:
#: At 0.70 it fires for a learner whose answers land near even odds throughout,
#: which is the case this engine is built to create. For everyone else the cap is
#: what stops the test, and that is the honest expectation: eight questions of a
#: one-parameter model place someone within roughly two thirds of a logit, not
#: to a decimal.
STOP_SE = 0.70

#: Never conclude from fewer than this many answers, however confident the
#: arithmetic looks: the first answer of a session is the one most likely to be
#: a misread question or a slipped tap.
MIN_QUESTIONS = 3

#: And never ask more than this, however uncertain we remain. Someone who came
#: to learn did not come to be measured, and an item bank too thin to place them
#: in eight questions will not manage it in twenty.
MAX_QUESTIONS = 8

#: Difficulty of 0 or 1 would be an infinite logit. Real items are never
#: certain either way.
_DIFFICULTY_FLOOR = 0.02
_DIFFICULTY_CEILING = 0.98


@dataclass(frozen=True, slots=True)
class Ability:
    """What we believe about one learner, as a normal posterior in logits."""

    mean: float = PRIOR_MEAN
    sd: float = PRIOR_SD

    @property
    def settled(self) -> bool:
        """Whether the belief is tight enough to place someone on."""
        return self.sd <= STOP_SE


def difficulty_logit(difficulty: float) -> float:
    """The product's 0-1 difficulty as a Rasch difficulty in logits.

    0.5 — an item half of learners fail — sits at 0, the middle of the scale, so
    an average learner meets an average item at even odds.
    """
    clamped = min(max(difficulty, _DIFFICULTY_FLOOR), _DIFFICULTY_CEILING)
    return math.log(clamped / (1.0 - clamped))


def probability_correct(ability: float, difficulty: float) -> float:
    """Rasch: the logistic of ability minus difficulty, both in logits."""
    return 1.0 / (1.0 + math.exp(-(ability - difficulty)))


def information(ability: float, difficulty: float) -> float:
    """How much an answer would tell us: ``p(1-p)``, peaking where they meet."""
    p = probability_correct(ability, difficulty)
    return p * (1.0 - p)


def update(ability: Ability, difficulty: float, *, correct: bool) -> Ability:
    """Fold one answer into the belief.

    A normal approximation to the Bayesian update: the answer's information adds
    to the precision, and the mean moves by the surprise — how far the outcome
    was from what we expected — scaled by how much we still did not know. Being
    right about a hard item moves it further than being right about an easy one,
    which is the whole reason to choose the item carefully.
    """
    p = probability_correct(ability.mean, difficulty)
    precision = 1.0 / (ability.sd**2) + p * (1.0 - p)
    variance = 1.0 / precision
    mean = ability.mean + variance * ((1.0 if correct else 0.0) - p)
    return Ability(mean=mean, sd=math.sqrt(variance))


def next_item[T](ability: Ability, candidates: dict[T, float]) -> T | None:
    """The candidate whose answer would tell us most, or None when there are none.

    ``candidates`` maps whatever identifies an item to its 0-1 difficulty. Ties
    break on the identifier so the same belief and the same bank always produce
    the same question — a diagnostic that varies under repetition cannot be
    debugged, and a learner who retakes it deserves the same start.
    """
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: (
            -information(ability.mean, difficulty_logit(candidates[item])),
            str(item),
        ),
    )


def should_stop(ability: Ability, asked: int) -> bool:
    """Whether enough has been asked.

    Long enough to mean something, short enough to be a beginning rather than an
    examination.
    """
    if asked >= MAX_QUESTIONS:
        return True
    if asked < MIN_QUESTIONS:
        return False
    return ability.settled
