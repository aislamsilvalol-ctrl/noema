"""Mastery Engine — concept-level understanding, derived from evidence.

Implements the model specified in ``docs/mastery-engine.md``. Pure functions over
frozen dataclasses, so a mastery score can always be recomputed from the append-only
evidence log rather than trusted as stored state.

The score is deliberately decomposable: :class:`Mastery` carries every intermediate
term, because a number the user cannot interrogate is a number they will not trust.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from noema.engines import fsrs

__all__ = [
    "Evidence",
    "Grader",
    "Mastery",
    "MasterySettings",
    "compute_mastery",
    "impact",
    "is_misconception",
]


class Grader(StrEnum):
    DETERMINISTIC = "deterministic"
    AI = "ai"
    SELF = "self"


@dataclass(frozen=True, slots=True)
class MasterySettings:
    """Every tunable in the model. Defaults are informed guesses, not fitted values."""

    recency_tau_days: float = 60.0
    prior_pseudo_count: float = 4.0
    prior_default_mean: float = 0.35
    retention_floor: float = 0.5  # lambda: share of mastery that survives forgetting
    fallback_stability_days: float = 3.0
    fallback_stability_exponent: float = 0.6
    grader_weights: tuple[float, float, float] = (1.0, 0.7, 0.4)
    misconception_confidence: int = 4
    impact_decay: float = 0.5


DEFAULTS: Final = MasterySettings()


@dataclass(frozen=True, slots=True)
class Evidence:
    """One graded interaction with a concept."""

    score: float  # correctness, partial credit allowed
    difficulty: float  # item difficulty, 0-1
    age_days: float
    grader: Grader
    confidence: int | None = None  # 1-5, optional

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"score must be in [0, 1], got {self.score}")
        if not 0.0 <= self.difficulty <= 1.0:
            raise ValueError(f"difficulty must be in [0, 1], got {self.difficulty}")
        if self.confidence is not None and not 1 <= self.confidence <= 5:
            raise ValueError(f"confidence must be in 1..5, got {self.confidence}")


@dataclass(frozen=True, slots=True)
class CardSnapshot:
    """FSRS state of one card attached to the concept."""

    state: fsrs.MemoryState
    elapsed_days: float
    coverage: float = 1.0  # how much of the concept this card tests


@dataclass(frozen=True, slots=True)
class Mastery:
    """A mastery score together with the terms that produced it."""

    score: float  # 0-100
    competence: float  # C
    retrievability: float  # R
    prior_mean: float
    effective_observations: float
    uncertainty: float  # posterior std-dev of C
    calibration: float  # -1..1, positive = overconfident

    @property
    def is_provisional(self) -> bool:
        """True when there is too little evidence to show a point estimate."""
        return self.effective_observations < 3.0


def compute_mastery(
    evidence: Sequence[Evidence],
    cards: Sequence[CardSnapshot] = (),
    prerequisite_masteries: Sequence[tuple[float, float]] = (),
    settings: MasterySettings = DEFAULTS,
) -> Mastery:
    """Compute mastery for one concept.

    Args:
        evidence: all graded interactions with the concept.
        cards: FSRS snapshots of cards attached to the concept, for retrievability.
        prerequisite_masteries: ``(mastery_0_100, edge_weight)`` pairs, used as the
            prior. A concept built on weak prerequisites starts pessimistic — which
            is what a tutor would assume, and it makes cold-start behave sensibly.
    """
    prior_mean = _prior_mean(prerequisite_masteries, settings)
    k = settings.prior_pseudo_count
    alpha, beta = k * prior_mean, k * (1 - prior_mean)

    weighted_successes = 0.0
    total_weight = 0.0
    for e in evidence:
        w = _evidence_weight(e, settings)
        weighted_successes += w * e.score
        total_weight += w

    alpha += weighted_successes
    beta += total_weight - weighted_successes
    competence = alpha / (alpha + beta)
    variance = (alpha * beta) / ((alpha + beta) ** 2 * (alpha + beta + 1))

    r = _retrievability(evidence, cards, settings)
    lam = settings.retention_floor
    score = 100.0 * competence * (lam + (1 - lam) * r)

    return Mastery(
        score=score,
        competence=competence,
        retrievability=r,
        prior_mean=prior_mean,
        effective_observations=total_weight,
        uncertainty=math.sqrt(variance),
        calibration=_calibration(evidence),
    )


def is_misconception(e: Evidence, settings: MasterySettings = DEFAULTS) -> bool:
    """A wrong answer given with high confidence.

    This is the failure mode plain spaced repetition never catches: the learner has a
    coherent wrong model and no reason to flag it for review.
    """
    return (
        e.score < 0.5
        and e.confidence is not None
        and e.confidence >= settings.misconception_confidence
    )


def impact(
    mastery_score: float,
    descendants_by_depth: Sequence[int],
    settings: MasterySettings = DEFAULTS,
) -> float:
    """Rank a weak concept by what it blocks, not by how low it scores.

    ``descendants_by_depth[i]`` is the number of concepts that depend on this one at
    ``i + 1`` prerequisite hops away.
    """
    reach = sum(
        settings.impact_decay ** (depth + 1) * count
        for depth, count in enumerate(descendants_by_depth)
    )
    return (1 - mastery_score / 100.0) * (1 + reach)


def _evidence_weight(e: Evidence, settings: MasterySettings) -> float:
    recency = math.exp(-e.age_days / settings.recency_tau_days)
    difficulty = 0.5 + e.difficulty
    deterministic, ai, self_reported = settings.grader_weights
    grader = {
        Grader.DETERMINISTIC: deterministic,
        Grader.AI: ai,
        Grader.SELF: self_reported,
    }[e.grader]
    return recency * difficulty * grader * _confidence_weight(e)


def _confidence_weight(e: Evidence) -> float:
    if e.confidence is None:
        return 1.0
    # A correct guess is weak evidence of knowing. A confident error is strong
    # evidence of not knowing, and is worth more than an ordinary miss.
    base = 0.5 if e.score >= 0.5 else 1.0
    return base + 0.125 * (e.confidence - 1)


def _prior_mean(
    prerequisite_masteries: Sequence[tuple[float, float]], settings: MasterySettings
) -> float:
    total_weight = sum(weight for _, weight in prerequisite_masteries)
    if total_weight <= 0:
        return settings.prior_default_mean
    weighted = sum(score / 100.0 * weight for score, weight in prerequisite_masteries)
    return weighted / total_weight


def _retrievability(
    evidence: Sequence[Evidence],
    cards: Sequence[CardSnapshot],
    settings: MasterySettings,
) -> float:
    if cards:
        total_coverage = sum(c.coverage for c in cards)
        if total_coverage > 0:
            return (
                sum(
                    c.coverage * fsrs.retrievability(c.state, c.elapsed_days)
                    for c in cards
                )
                / total_coverage
            )

    if not evidence:
        return 0.0

    # No cards yet: decay from the most recent evidence, with a half-life that grows
    # as successful recalls accumulate.
    successes = sum(1 for e in evidence if e.score >= 0.5)
    stability = settings.fallback_stability_days * (1 + successes) ** (
        settings.fallback_stability_exponent
    )
    return math.exp(-min(e.age_days for e in evidence) / stability)


def _calibration(evidence: Sequence[Evidence]) -> float:
    rated = [e for e in evidence if e.confidence is not None]
    if not rated:
        return 0.0
    return sum(
        (e.confidence - 1) / 4.0 - e.score  # type: ignore[operator]
        for e in rated
    ) / len(rated)
