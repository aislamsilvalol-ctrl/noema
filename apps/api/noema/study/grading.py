"""Grading answers.

Deterministic where the type allows it — an MCQ has a right option and no judgement
is involved. AI grading only for open answers, and never as string comparison: the
question is whether the learner demonstrated the understanding, not whether they
used the same words as the source.

The deterministic half is pure, so it is testable without a model.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from noema.db.models import Difficulty, Grader, QuestionType

__all__ = ["Grade", "difficulty_weight", "grade_deterministic", "is_gradeable_locally"]

#: Item difficulty as the mastery engine wants it: 0 to 1. Getting an expert item
#: right is more informative than getting an easy one right, and this is what makes
#: that true in the numbers rather than only in the documentation.
DIFFICULTY_WEIGHTS: dict[Difficulty, float] = {
    Difficulty.EASY: 0.2,
    Difficulty.MEDIUM: 0.5,
    Difficulty.HARD: 0.75,
    Difficulty.EXPERT: 0.95,
}

LOCALLY_GRADEABLE = {
    QuestionType.MCQ,
    QuestionType.TRUE_FALSE,
    QuestionType.FILL_BLANK,
    QuestionType.MATCHING,
    QuestionType.ORDERING,
}

PUNCTUATION = re.compile(r"[^\w\s]")
WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class Grade:
    score: float
    is_correct: bool
    grader: Grader
    feedback: dict[str, Any] = field(default_factory=dict)


def difficulty_weight(difficulty: Difficulty) -> float:
    return DIFFICULTY_WEIGHTS.get(difficulty, 0.5)


def is_gradeable_locally(question_type: QuestionType) -> bool:
    return question_type in LOCALLY_GRADEABLE


def grade_deterministic(
    question_type: QuestionType, payload: dict[str, Any], response: dict[str, Any]
) -> Grade:
    """Grade a question whose answer is unambiguous."""
    if question_type is QuestionType.MCQ:
        return _grade_mcq(payload, response)
    if question_type is QuestionType.TRUE_FALSE:
        return _grade_true_false(payload, response)
    if question_type is QuestionType.FILL_BLANK:
        return _grade_fill_blank(payload, response)
    if question_type is QuestionType.MATCHING:
        return _grade_matching(payload, response)
    if question_type is QuestionType.ORDERING:
        return _grade_ordering(payload, response)

    raise ValueError(f"{question_type} needs semantic grading, not this function")


def _grade_mcq(payload: dict[str, Any], response: dict[str, Any]) -> Grade:
    correct = payload.get("correct_index")
    chosen = response.get("choice")
    right = correct is not None and chosen == correct

    return Grade(
        score=1.0 if right else 0.0,
        is_correct=right,
        grader=Grader.DETERMINISTIC,
        feedback={
            "correct_index": correct,
            # The explanation matters more than the verdict: being told you are
            # wrong without being told why teaches nothing.
            "explanation": payload.get("explanation", ""),
        },
    )


def _grade_true_false(payload: dict[str, Any], response: dict[str, Any]) -> Grade:
    # "answer" absent (never answered, e.g. a skipped exam question) must never
    # grade as correct. Every other question type's missing-response default
    # structurally can't equal a real answer (None, "", {}, []) — but bool(None)
    # coerces "unanswered" into a valid False, which matched a False correct
    # answer and gave a skipped question free credit.
    right = "answer" in response and bool(payload.get("answer")) is bool(
        response["answer"]
    )
    return Grade(
        score=1.0 if right else 0.0,
        is_correct=right,
        grader=Grader.DETERMINISTIC,
        feedback={"explanation": payload.get("explanation", "")},
    )


def _grade_fill_blank(payload: dict[str, Any], response: dict[str, Any]) -> Grade:
    """Accept any of the listed answers, ignoring case, accents and punctuation.

    A learner who wrote the right word with a typo in the accent knows the thing.
    Anything beyond that is a judgement call, and judgement calls go to the model.
    """
    accepted = {_fold(str(a)) for a in payload.get("accepted", []) if str(a).strip()}
    given = _fold(str(response.get("text", "")))
    right = bool(given) and given in accepted

    return Grade(
        score=1.0 if right else 0.0,
        is_correct=right,
        grader=Grader.DETERMINISTIC,
        feedback={"accepted": sorted(accepted)},
    )


def _grade_matching(payload: dict[str, Any], response: dict[str, Any]) -> Grade:
    """Partial credit per pair: getting three of four right is not the same as zero."""
    pairs = payload.get("pairs", {})
    given = response.get("pairs", {})
    if not isinstance(pairs, dict) or not pairs:
        return Grade(0.0, False, Grader.DETERMINISTIC, {"reason": "no pairs defined"})

    correct = sum(1 for key, value in pairs.items() if given.get(key) == value)
    score = correct / len(pairs)

    return Grade(
        score=score,
        is_correct=score == 1.0,
        grader=Grader.DETERMINISTIC,
        feedback={
            "correct": correct,
            "total": len(pairs),
            "wrong_keys": [k for k, v in pairs.items() if given.get(k) != v],
        },
    )


def _grade_ordering(payload: dict[str, Any], response: dict[str, Any]) -> Grade:
    """Score by how many items are in their right place.

    Not all-or-nothing: an ordering with one pair swapped shows far more
    understanding than a random permutation, and scoring both zero would tell the
    mastery model they are the same.
    """
    expected = payload.get("order", [])
    given = response.get("order", [])
    if not isinstance(expected, list) or not expected:
        return Grade(0.0, False, Grader.DETERMINISTIC, {"reason": "no order defined"})

    in_place = sum(
        1
        for index, item in enumerate(expected)
        if index < len(given) and given[index] == item
    )
    score = in_place / len(expected)

    return Grade(
        score=score,
        is_correct=score == 1.0,
        grader=Grader.DETERMINISTIC,
        feedback={"correct_positions": in_place, "total": len(expected)},
    )


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in normalized if not unicodedata.combining(c))
    return WHITESPACE.sub(" ", PUNCTUATION.sub(" ", stripped.lower())).strip()
