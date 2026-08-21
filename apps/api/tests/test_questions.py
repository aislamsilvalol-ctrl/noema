"""Turning a model's raw response into questions worth answering.

Pure by design — no database, no gateway. A malformed question is worse than a
missing one: an MCQ with a bad correct_index would grade a right answer wrong,
so every type-specific shape is validated before it can ever reach a learner.
"""

from __future__ import annotations

from noema.db.models import Difficulty, QuestionType
from noema.study.questions import MAX_PROMPT, MAX_QUESTIONS_PER_BATCH, parse_questions


def mcq(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "type": "mcq",
        "prompt": "Which phase fills the ventricles?",
        "options": ["Diastole", "Systole"],
        "correct_index": 0,
        "difficulty": "medium",
        "concept": "Cardiac Cycle",
        "explanation": "Diastole is the filling phase.",
    }
    base.update(overrides)
    return base


def test_a_well_formed_mcq_comes_through() -> None:
    questions = parse_questions({"questions": [mcq()]})

    assert len(questions) == 1
    q = questions[0]
    assert q.type is QuestionType.MCQ
    assert q.difficulty is Difficulty.MEDIUM
    assert q.concept_name == "Cardiac Cycle"
    assert q.payload["options"] == ["Diastole", "Systole"]
    assert q.payload["correct_index"] == 0


def test_a_missing_questions_key_is_no_questions_not_an_error() -> None:
    assert parse_questions({}) == []


def test_a_non_list_questions_value_is_no_questions() -> None:
    assert parse_questions({"questions": "not a list"}) == []


def test_a_non_dict_item_is_skipped() -> None:
    questions = parse_questions({"questions": ["not a dict", mcq()]})

    assert len(questions) == 1


def test_an_unrecognised_type_is_skipped() -> None:
    assert parse_questions({"questions": [mcq(type="essay")]}) == []


def test_an_empty_prompt_is_skipped() -> None:
    assert parse_questions({"questions": [mcq(prompt="")]}) == []
    assert parse_questions({"questions": [mcq(prompt="   ")]}) == []


def test_the_prompt_is_truncated_to_its_limit() -> None:
    questions = parse_questions({"questions": [mcq(prompt="Q" * (MAX_PROMPT + 50))]})

    assert len(questions[0].prompt) == MAX_PROMPT


def test_the_concept_name_is_truncated_to_200_characters() -> None:
    questions = parse_questions({"questions": [mcq(concept="x" * 250)]})

    assert len(questions[0].concept_name) == 200


def test_only_the_first_batch_limit_worth_of_questions_survive() -> None:
    raw = [mcq(prompt=f"Q{i}") for i in range(MAX_QUESTIONS_PER_BATCH + 5)]
    questions = parse_questions({"questions": raw})

    assert len(questions) == MAX_QUESTIONS_PER_BATCH
    assert questions[0].prompt == "Q0"


def test_an_mcq_with_fewer_than_two_options_is_skipped() -> None:
    assert parse_questions({"questions": [mcq(options=["Only one"])]}) == []


def test_an_mcq_with_an_out_of_range_correct_index_is_skipped() -> None:
    assert parse_questions({"questions": [mcq(correct_index=5)]}) == []


def test_an_mcq_with_a_non_integer_correct_index_is_skipped() -> None:
    assert parse_questions({"questions": [mcq(correct_index="0")]}) == []


def test_a_well_formed_true_false_comes_through() -> None:
    item = mcq(type="true_false", answer=True)
    del item["options"]
    del item["correct_index"]

    questions = parse_questions({"questions": [item]})

    assert len(questions) == 1
    assert questions[0].type is QuestionType.TRUE_FALSE
    assert questions[0].payload["answer"] is True


def test_a_true_false_with_a_non_boolean_answer_is_skipped() -> None:
    item = mcq(type="true_false", answer="yes")
    del item["options"]
    del item["correct_index"]

    assert parse_questions({"questions": [item]}) == []


def test_a_well_formed_fill_blank_comes_through() -> None:
    item = mcq(type="fill_blank", accepted=["mitochondria", "the mitochondria"])
    del item["options"]
    del item["correct_index"]

    questions = parse_questions({"questions": [item]})

    assert len(questions) == 1
    assert questions[0].payload["accepted"] == ["mitochondria", "the mitochondria"]


def test_a_fill_blank_with_no_accepted_answers_is_skipped() -> None:
    item = mcq(type="fill_blank", accepted=[])
    del item["options"]
    del item["correct_index"]

    assert parse_questions({"questions": [item]}) == []


def test_a_well_formed_ordering_comes_through() -> None:
    item = mcq(type="ordering", order=["First", "Second", "Third"])
    del item["options"]
    del item["correct_index"]

    questions = parse_questions({"questions": [item]})

    assert len(questions) == 1
    assert questions[0].payload["order"] == ["First", "Second", "Third"]


def test_an_ordering_with_fewer_than_two_items_is_skipped() -> None:
    item = mcq(type="ordering", order=["Only one"])
    del item["options"]
    del item["correct_index"]

    assert parse_questions({"questions": [item]}) == []


def test_a_well_formed_open_question_comes_through_with_a_rubric() -> None:
    item = mcq(type="open", rubric_points=["mentions the chain rule"])
    del item["options"]
    del item["correct_index"]

    questions = parse_questions({"questions": [item]})

    assert len(questions) == 1
    assert questions[0].type is QuestionType.OPEN
    assert questions[0].rubric == {"points": ["mentions the chain rule"]}


def test_an_open_question_with_no_rubric_points_still_parses_with_no_rubric() -> None:
    """Filtering an ungradeable open question out is storage's job, not parsing's."""
    item = mcq(type="open")
    del item["options"]
    del item["correct_index"]

    questions = parse_questions({"questions": [item]})

    assert len(questions) == 1
    assert questions[0].rubric is None


def test_an_unrecognised_difficulty_falls_back_to_medium() -> None:
    questions = parse_questions({"questions": [mcq(difficulty="impossible")]})

    assert questions[0].difficulty is Difficulty.MEDIUM


def test_a_missing_difficulty_falls_back_to_medium() -> None:
    item = mcq()
    del item["difficulty"]

    questions = parse_questions({"questions": [item]})

    assert questions[0].difficulty is Difficulty.MEDIUM


def test_every_recognised_difficulty_maps_correctly() -> None:
    for raw, expected in (
        ("easy", Difficulty.EASY),
        ("medium", Difficulty.MEDIUM),
        ("hard", Difficulty.HARD),
        ("expert", Difficulty.EXPERT),
    ):
        questions = parse_questions({"questions": [mcq(difficulty=raw)]})
        assert questions[0].difficulty is expected, raw
