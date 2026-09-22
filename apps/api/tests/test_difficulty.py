"""Observed item difficulty.

Pure functions, so the rule that decides whether the data or the author gets to
say how hard an item is can be tested without a database.
"""

from __future__ import annotations

import pytest

from noema.db.models import Difficulty
from noema.engines.difficulty import (
    MIN_OBSERVATIONS,
    PRIOR_WEIGHT,
    item_difficulty,
    smoothed_difficulty,
)
from noema.study.grading import difficulty_weight, question_difficulty

# ── Smoothing ─────────────────────────────────────────────────────────────────


def test_no_answers_is_exactly_the_prior() -> None:
    assert smoothed_difficulty(0, 0, prior=0.75) == 0.75


def test_one_wrong_answer_does_not_swing_to_one() -> None:
    """The whole point: an item answered once must not become "expert"."""
    value = smoothed_difficulty(1, 1, prior=0.5)
    assert 0.5 < value < 0.7


def test_one_right_answer_does_not_swing_to_zero() -> None:
    value = smoothed_difficulty(0, 1, prior=0.5)
    assert 0.3 < value < 0.5


def test_many_answers_converge_on_the_raw_rate() -> None:
    value = smoothed_difficulty(900, 1000, prior=0.2)
    assert value == pytest.approx(0.9, abs=0.01)


def test_the_prior_is_worth_prior_weight_answers() -> None:
    """After exactly PRIOR_WEIGHT real answers the data and the author tie."""
    n = int(PRIOR_WEIGHT)
    assert smoothed_difficulty(n, n, prior=0.0) == pytest.approx(0.5)


def test_more_wrong_answers_means_harder() -> None:
    values = [smoothed_difficulty(w, 20, prior=0.5) for w in range(21)]
    assert values == sorted(values)
    assert all(0.0 <= v <= 1.0 for v in values)


@pytest.mark.parametrize(("wrong", "total"), [(-1, 5), (6, 5), (0, -1)])
def test_impossible_counts_are_rejected(wrong: int, total: int) -> None:
    with pytest.raises(ValueError):
        smoothed_difficulty(wrong, total, prior=0.5)


def test_a_prior_outside_the_unit_interval_is_rejected() -> None:
    with pytest.raises(ValueError):
        smoothed_difficulty(0, 0, prior=1.5)


# ── Which value wins ──────────────────────────────────────────────────────────


def test_no_observation_uses_the_declared_value() -> None:
    assert item_difficulty(0.75, None, None) == 0.75


def test_below_the_threshold_the_declared_value_still_wins() -> None:
    assert item_difficulty(0.75, 0.1, MIN_OBSERVATIONS - 1) == 0.75


def test_at_the_threshold_the_observed_value_wins() -> None:
    assert item_difficulty(0.75, 0.1, MIN_OBSERVATIONS) == 0.1


def test_the_observed_value_is_clamped() -> None:
    assert item_difficulty(0.5, 1.4, MIN_OBSERVATIONS) == 1.0


def test_question_difficulty_falls_back_to_the_enum_weight() -> None:
    declared = difficulty_weight(Difficulty.HARD)
    assert question_difficulty(Difficulty.HARD, None, None) == declared
    assert question_difficulty(Difficulty.HARD, 0.05, 2) == declared
    assert question_difficulty(Difficulty.HARD, 0.05, MIN_OBSERVATIONS) == 0.05
