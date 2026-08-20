"""When a misconception counts as corrected, and what a drill question needs to
be gradeable.

The spacing rule is the whole idea, and it is pure arithmetic over timestamps, so
it can be tested without a database: two correct confident answers, far enough
apart that the second is evidence of memory rather than of the first still being
in the room. `_build` is pure too — it validates a model's raw drill payload into
a storable `Question`, given ORM objects that never need to touch a session.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from noema.db.models import Difficulty, Mistake, Question, QuestionType
from noema.study.correction import SPACING, _build, _spaced_enough

NOON = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def test_one_correction_is_not_enough() -> None:
    """A single right answer is a coin landing the right way up."""
    assert _spaced_enough([NOON]) is False


def test_two_in_the_same_sitting_are_not_enough() -> None:
    """That is the last explanation still echoing, not a changed model."""
    assert _spaced_enough([NOON, NOON + timedelta(minutes=4)]) is False


def test_two_a_day_apart_resolve_it() -> None:
    assert _spaced_enough([NOON, NOON + timedelta(days=1)]) is True


def test_the_gap_is_measured_from_the_first_correction() -> None:
    """Three answers in one sitting then one the next day still counts.

    The learner did answer correctly a day later; that the middle attempts were
    bunched up does not make the last one worth less.
    """
    moments = [
        NOON,
        NOON + timedelta(minutes=2),
        NOON + timedelta(minutes=5),
        NOON + timedelta(days=1),
    ]
    assert _spaced_enough(moments) is True


def test_just_under_the_gap_does_not_count() -> None:
    """The boundary is a decision, so it is pinned rather than left to drift."""
    assert _spaced_enough([NOON, NOON + SPACING - timedelta(minutes=1)]) is False
    assert _spaced_enough([NOON, NOON + SPACING]) is True


def test_nothing_at_all_is_not_a_correction() -> None:
    assert _spaced_enough([]) is False


NOTEBOOK_ID = uuid.uuid4()
CONCEPT_ID = uuid.uuid4()
SOURCE_CHUNK_IDS = [uuid.uuid4(), uuid.uuid4()]


def drill(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "type": "mcq",
        "prompt": "Which phase fills the ventricles?",
        "options": ["Diastole", "Systole"],
        "correct_index": 0,
        "explanation": "Diastole is the filling phase.",
        "discriminates": "Distinguishes filling from ejection.",
    }
    base.update(overrides)
    return base


def original_question() -> Question:
    return Question(notebook_id=NOTEBOOK_ID, source_chunk_ids=SOURCE_CHUNK_IDS)


def mistake_for(concept_id: uuid.UUID | None = CONCEPT_ID) -> Mistake:
    return Mistake(concept_id=concept_id)


def test_a_valid_mcq_becomes_a_gradeable_question() -> None:
    question = _build(drill(), original_question(), mistake_for(), uuid.uuid4())

    assert question is not None
    assert question.type is QuestionType.MCQ
    assert question.difficulty is Difficulty.HARD
    assert question.notebook_id == NOTEBOOK_ID
    assert question.concept_id == CONCEPT_ID
    assert question.source_chunk_ids == SOURCE_CHUNK_IDS
    assert question.payload["options"] == ["Diastole", "Systole"]
    assert question.payload["correct_index"] == 0


def test_a_valid_true_false_becomes_a_gradeable_question() -> None:
    item = drill(type="true_false", answer=True)
    del item["options"]
    del item["correct_index"]

    question = _build(item, original_question(), mistake_for(), uuid.uuid4())

    assert question is not None
    assert question.type is QuestionType.TRUE_FALSE
    assert question.payload["answer"] is True


def test_an_empty_prompt_is_not_gradeable() -> None:
    assert (
        _build(drill(prompt=""), original_question(), mistake_for(), uuid.uuid4()) is None
    )
    assert (
        _build(drill(prompt="   "), original_question(), mistake_for(), uuid.uuid4())
        is None
    )


def test_an_unrecognised_type_is_not_gradeable() -> None:
    item = drill(type="fill_blank")
    assert _build(item, original_question(), mistake_for(), uuid.uuid4()) is None


def test_an_mcq_with_fewer_than_two_options_is_not_gradeable() -> None:
    item = drill(options=["Only one"])
    assert _build(item, original_question(), mistake_for(), uuid.uuid4()) is None


def test_an_mcq_whose_correct_index_is_out_of_range_is_not_gradeable() -> None:
    item = drill(correct_index=5)
    assert _build(item, original_question(), mistake_for(), uuid.uuid4()) is None


def test_an_mcq_whose_correct_index_is_not_an_integer_is_not_gradeable() -> None:
    item = drill(correct_index="0")
    assert _build(item, original_question(), mistake_for(), uuid.uuid4()) is None


def test_a_true_false_with_a_non_boolean_answer_is_not_gradeable() -> None:
    item = drill(type="true_false", answer="yes")
    del item["options"]
    del item["correct_index"]
    assert _build(item, original_question(), mistake_for(), uuid.uuid4()) is None


def test_a_question_with_no_concept_carries_no_concept_id() -> None:
    question = _build(
        drill(), original_question(), mistake_for(concept_id=None), uuid.uuid4()
    )

    assert question is not None
    assert question.concept_id is None
