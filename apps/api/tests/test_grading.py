"""Deterministic grading.

Pure functions, so the rules that decide whether a learner is told they were wrong
are testable without a model.
"""

from __future__ import annotations

from typing import Any

import pytest

from noema.db.models import Difficulty, Grader, QuestionType
from noema.study.grading import (
    Grade,
    difficulty_weight,
    grade_deterministic,
    is_gradeable_locally,
)


def grade(kind: QuestionType, payload: dict[str, Any], response: dict[str, Any]) -> Grade:
    return grade_deterministic(kind, payload, response)


# ── Multiple choice ───────────────────────────────────────────────────────────


def test_the_right_option_scores_one() -> None:
    result = grade(QuestionType.MCQ, {"correct_index": 2}, {"choice": 2})
    assert result.score == 1.0
    assert result.is_correct
    assert result.grader is Grader.DETERMINISTIC


def test_a_wrong_option_returns_the_explanation_not_just_a_verdict() -> None:
    """Being told you are wrong without being told why teaches nothing."""
    result = grade(
        QuestionType.MCQ,
        {"correct_index": 2, "explanation": "The gradient points uphill."},
        {"choice": 0},
    )
    assert result.score == 0.0
    assert result.feedback["explanation"] == "The gradient points uphill."


def test_no_answer_is_not_a_correct_answer() -> None:
    assert grade(QuestionType.MCQ, {"correct_index": 1}, {}).score == 0.0


# ── True / false ──────────────────────────────────────────────────────────────


def test_true_false_compares_booleans() -> None:
    assert grade(QuestionType.TRUE_FALSE, {"answer": True}, {"answer": True}).is_correct
    assert not grade(
        QuestionType.TRUE_FALSE, {"answer": True}, {"answer": False}
    ).is_correct


# ── Fill in the blank ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "given",
    ["gradient descent", "Gradient Descent", "  gradient descent  ", "gradient-descent"],
)
def test_case_spacing_and_punctuation_do_not_decide_correctness(given: str) -> None:
    """A learner who wrote the right word with a stray hyphen knows the thing."""
    result = grade(
        QuestionType.FILL_BLANK, {"accepted": ["gradient descent"]}, {"text": given}
    )
    assert result.is_correct


def test_accents_are_folded() -> None:
    result = grade(
        QuestionType.FILL_BLANK, {"accepted": ["Fourier"]}, {"text": "fourièr"}
    )
    assert result.is_correct


def test_any_accepted_answer_counts() -> None:
    payload = {"accepted": ["backpropagation", "backprop"]}
    assert grade(QuestionType.FILL_BLANK, payload, {"text": "backprop"}).is_correct


def test_a_different_word_is_wrong() -> None:
    result = grade(
        QuestionType.FILL_BLANK, {"accepted": ["gradient"]}, {"text": "derivative"}
    )
    assert not result.is_correct


def test_an_empty_answer_is_wrong_even_if_nothing_was_accepted() -> None:
    assert not grade(QuestionType.FILL_BLANK, {"accepted": []}, {"text": ""}).is_correct


# ── Matching ──────────────────────────────────────────────────────────────────


def test_matching_gives_partial_credit() -> None:
    """Three of four right is not the same as zero, and the mastery model needs to
    be told the difference."""
    payload = {"pairs": {"a": "1", "b": "2", "c": "3", "d": "4"}}
    response = {"pairs": {"a": "1", "b": "2", "c": "3", "d": "9"}}

    result = grade(QuestionType.MATCHING, payload, response)

    assert result.score == 0.75
    assert not result.is_correct
    assert result.feedback["wrong_keys"] == ["d"]


def test_all_pairs_right_is_correct() -> None:
    payload = {"pairs": {"a": "1", "b": "2"}}
    result = grade(QuestionType.MATCHING, payload, {"pairs": {"a": "1", "b": "2"}})
    assert result.score == 1.0 and result.is_correct


def test_a_question_with_no_pairs_scores_zero_rather_than_dividing_by_zero() -> None:
    assert grade(QuestionType.MATCHING, {"pairs": {}}, {"pairs": {}}).score == 0.0


# ── Ordering ──────────────────────────────────────────────────────────────────


def test_ordering_scores_by_position() -> None:
    """One swapped pair shows far more understanding than a random permutation."""
    payload = {"order": ["a", "b", "c", "d"]}

    perfect = grade(QuestionType.ORDERING, payload, {"order": ["a", "b", "c", "d"]})
    swapped = grade(QuestionType.ORDERING, payload, {"order": ["a", "b", "d", "c"]})
    reversed_ = grade(QuestionType.ORDERING, payload, {"order": ["d", "c", "b", "a"]})

    assert perfect.score == 1.0
    assert 0 < swapped.score < 1.0
    assert reversed_.score < swapped.score


def test_a_short_answer_does_not_crash_the_comparison() -> None:
    payload = {"order": ["a", "b", "c"]}
    assert grade(QuestionType.ORDERING, payload, {"order": ["a"]}).score == pytest.approx(
        1 / 3
    )


# ── Routing ───────────────────────────────────────────────────────────────────


def test_open_answers_are_not_graded_locally() -> None:
    assert not is_gradeable_locally(QuestionType.OPEN)
    with pytest.raises(ValueError, match="semantic"):
        grade(QuestionType.OPEN, {}, {"text": "something"})


@pytest.mark.parametrize(
    "kind",
    [
        QuestionType.MCQ,
        QuestionType.TRUE_FALSE,
        QuestionType.FILL_BLANK,
        QuestionType.MATCHING,
        QuestionType.ORDERING,
    ],
)
def test_unambiguous_types_are_graded_locally(kind: QuestionType) -> None:
    assert is_gradeable_locally(kind)


# ── Difficulty ────────────────────────────────────────────────────────────────


def test_difficulty_weights_increase_with_difficulty() -> None:
    """The mastery engine weights harder items more; this is where that becomes real
    rather than documented."""
    weights = [
        difficulty_weight(d)
        for d in (Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD, Difficulty.EXPERT)
    ]
    assert weights == sorted(weights)
    assert all(0 <= w <= 1 for w in weights)
