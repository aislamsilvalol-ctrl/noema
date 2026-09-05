"""The Professor Engine's pure parts: router, blocks, budget, projection,
curriculum, memory, assessment grading. No database, no model."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

import pytest

from noema.professor import assessment, budget, curriculum, memory, moves
from noema.professor.blocks import BlockFilter, validate_block
from noema.professor.intent import fallback_goal
from noema.professor.student import project, render_knowledge

# ── moves ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("message", "signal"),
    [
        ("Não entendi.", moves.Signal.CONFUSED),
        ("não entendi o exemplo", moves.Signal.CONFUSED),
        ("Isso eu já sei.", moves.Signal.KNOWS),
        ("Me testa.", moves.Signal.WANTS_PRACTICE),
        ("quero fazer uma prova", moves.Signal.WANTS_EXAM),
        ("faz um resumo", moves.Signal.WANTS_SUMMARY),
        ("dá um exemplo", moves.Signal.WANTS_EXAMPLE),
        ("aprofunda isso", moves.Signal.WANTS_DEPTH),
        ("cria flashcards disso", moves.Signal.WANTS_FLASHCARDS),
        ("tô cansado, chega por hoje", moves.Signal.TIRED),
        ("O que é o id?", moves.Signal.NEUTRAL),
    ],
)
def test_unambiguous_phrasings_are_read_without_a_model(
    message: str, signal: moves.Signal
) -> None:
    assert moves.read_signal(message) is signal


def test_first_contact_teaches_and_asks() -> None:
    d = moves.decide(moves.Signal.NEUTRAL, moves.Situation(first_turn=True))
    assert d.move is moves.Move.TEACH
    assert d.require_check is True
    assert d.mino == "teaching"


def test_confusion_switches_strategy_instead_of_repeating() -> None:
    d = moves.decide(moves.Signal.CONFUSED, moves.Situation(last_strategy="definition"))
    assert d.move is moves.Move.CORRECT
    assert d.strategy == "analogy"
    again = moves.decide(moves.Signal.CONFUSED, moves.Situation(last_strategy="analogy"))
    assert again.strategy == "scenario"


def test_the_ladder_never_returns_to_the_definition_that_failed() -> None:
    assert moves.next_strategy("socratic") == "analogy"
    assert moves.next_strategy("unknown") == "analogy"


def test_already_knows_skips_ahead() -> None:
    d = moves.decide(moves.Signal.KNOWS, moves.Situation())
    assert d.move is moves.Move.ADVANCE


def test_a_wrong_quiz_answer_is_corrected_and_two_make_mino_concerned() -> None:
    once = moves.decide(
        moves.Signal.NEUTRAL,
        moves.Situation(event_kind="quiz", event_correct=False, wrong_streak=1),
    )
    assert once.move is moves.Move.CORRECT
    assert once.mino == "correcting"
    twice = moves.decide(
        moves.Signal.NEUTRAL,
        moves.Situation(event_kind="quiz", event_correct=False, wrong_streak=2),
    )
    assert twice.mino == "concerned"


def test_a_right_quiz_answer_advances() -> None:
    d = moves.decide(
        moves.Signal.NEUTRAL, moves.Situation(event_kind="quiz", event_correct=True)
    )
    assert d.move is moves.Move.ADVANCE
    assert d.signal is moves.Signal.RIGHT


def test_a_message_after_a_question_is_an_answer_to_grade() -> None:
    d = moves.decide(moves.Signal.NEUTRAL, moves.Situation(last_move="question"))
    assert d.move is moves.Move.CORRECT
    assert d.signal is moves.Signal.ANSWERING


def test_a_checkpoint_is_due_only_at_a_boundary_and_a_check_is_forced() -> None:
    exam = moves.decide(moves.Signal.NEUTRAL, moves.Situation(checkpoint_due=True))
    assert exam.move is moves.Move.EXAM
    disabled = moves.decide(
        moves.Signal.NEUTRAL,
        moves.Situation(checkpoint_due=True, assessments_enabled=False),
    )
    assert disabled.move is moves.Move.TEACH
    check = moves.decide(moves.Signal.NEUTRAL, moves.Situation(since_check=3))
    assert check.move is moves.Move.QUESTION


def test_an_assessment_with_weak_concepts_corrects_them_first() -> None:
    d = moves.decide(
        moves.Signal.NEUTRAL,
        moves.Situation(event_kind="assessment", remediation=("recalque",)),
    )
    assert d.move is moves.Move.CORRECT
    assert d.remediation == ("recalque",)
    assert d.tier.value == "premium"


def test_every_move_has_a_tier_a_mino_state_and_a_legacy_intent() -> None:
    for move in moves.Move:
        assert move in moves.MOVE_TIER
        assert move in moves.MOVE_MINO
        assert move in moves.MOVE_INTENT


# ── blocks ────────────────────────────────────────────────────────────────

QUIZ = (
    '```noema:quiz\n{"question": "Onde?", "options": ["A", "B"], "answer": 1, '
    '"explain": "porque", "concept": "recalque"}\n```'
)


def test_a_block_is_split_from_the_prose_even_across_chunks() -> None:
    f = BlockFilter()
    text = "Olha isso.\n\n" + QUIZ + "\nE agora?"
    visible: list[str] = []
    blocks = []
    for i in range(0, len(text), 7):
        shown, found = f.feed(text[i : i + 7])
        visible.append(shown)
        blocks.extend(found)
    visible.append(f.flush())
    assert "".join(visible) == "Olha isso.\n\nE agora?"
    assert [b.tool for b in blocks] == ["quiz"]
    assert blocks[0].data["answer"] == 1
    assert blocks[0].data["concept"] == "recalque"


def test_a_stray_backtick_is_delayed_not_lost() -> None:
    f = BlockFilter()
    shown, _ = f.feed("use `")
    tail = f.flush()
    assert shown + tail == "use `"


def test_a_malformed_block_is_dropped_never_shown_raw() -> None:
    f = BlockFilter()
    shown, found = f.feed("Antes.\n```noema:quiz\n{not json\n```\nDepois.")
    assert shown + f.flush() == "Antes.\nDepois."
    assert found == []


def test_an_unclosed_block_at_the_end_is_dropped() -> None:
    f = BlockFilter()
    shown, _ = f.feed('Prose.\n```noema:layers\n{"title": "x"')
    assert shown == "Prose.\n"
    assert f.flush() == ""


def test_the_rubric_of_a_check_never_reaches_the_client() -> None:
    block = validate_block(
        "check", '{"question": "Explica.", "rubric": ["a", "b"], "concept": "id"}'
    )
    assert block is not None
    assert "rubric" not in block.public()
    assert block.as_record()["data"]["rubric"] == ["a", "b"]


def test_a_quiz_whose_answer_is_out_of_range_is_invalid() -> None:
    assert (
        validate_block("quiz", '{"question": "?", "options": ["a"], "answer": 3}') is None
    )
    assert validate_block("nope", "{}") is None


# ── budget ────────────────────────────────────────────────────────────────


class _Turn:
    def __init__(self, content: str) -> None:
        self.content = content
        self.token_estimate = len(content) // 4


def test_the_newest_turns_fit_first_and_the_newest_always_rides() -> None:
    turns = [_Turn("a" * 400), _Turn("b" * 400), _Turn("c" * 400), _Turn("d" * 4000)]
    kept, dropped = budget.fit_transcript(turns, 250)
    assert [t.content[0] for t in kept] == ["d"]
    assert dropped == 3
    kept, dropped = budget.fit_transcript(turns[:3], 250)
    assert [t.content[0] for t in kept] == ["b", "c"]
    assert dropped == 1


def test_the_report_totals_its_components() -> None:
    report = budget.ContextReport(system=10, transcript=20, memory=5, student=5)
    assert report.total == 40
    assert report.as_dict()["total"] == 40


# ── student projection ────────────────────────────────────────────────────

NOW = datetime(2026, 9, 5, tzinfo=UTC)


def test_reading_is_not_showing() -> None:
    p = project([], introduced=True, last_at=None)
    assert p.stage == "introduced"
    assert p.evidence_count == 0


def test_recent_answers_weigh_more_than_old_ones() -> None:
    improving = project(
        [("quiz", 0.0), ("quiz", 0.0), ("quiz", 1.0), ("check", 1.0)],
        introduced=True,
        last_at=NOW,
    )
    declining = project(
        [("check", 1.0), ("quiz", 1.0), ("quiz", 0.0), ("quiz", 0.0)],
        introduced=True,
        last_at=NOW,
    )
    assert improving.score > declining.score
    assert improving.correct_streak == 2
    assert declining.wrong_streak == 2


def test_mastery_needs_strong_evidence_not_the_professors_word() -> None:
    chat_only = project(
        [("conversation", 1.0)] * 4, introduced=True, last_at=datetime.now(UTC)
    )
    assert chat_only.stage == "learning"
    with_check = project(
        [("conversation", 1.0)] * 3 + [("check", 1.0)],
        introduced=True,
        last_at=datetime.now(UTC),
    )
    assert with_check.stage == "mastered"


def test_two_wrong_answers_make_a_concept_uncertain() -> None:
    assert project(
        [("quiz", 0.0), ("quiz", 0.0)], introduced=True, last_at=NOW
    ).stage == ("uncertain")


def test_render_knowledge_is_empty_when_nothing_is_known() -> None:
    assert render_knowledge([], profile={}) == ""


# ── curriculum ────────────────────────────────────────────────────────────


def _plan() -> dict[str, Any]:
    return curriculum.validate_plan(
        {
            "modules": [
                {
                    "title": "Fundamentos",
                    "lessons": [
                        {
                            "title": "O inconsciente",
                            "concepts": ["inconsciente", "lapso"],
                        },
                        {"title": "Recalque", "concepts": ["recalque"]},
                    ],
                },
                {"title": "Estrutura", "lessons": [{"title": "Id", "concepts": ["id"]}]},
                {"title": "vazio", "lessons": []},
            ]
        }
    )


def test_validation_keeps_well_formed_lessons_and_marks_the_first_current() -> None:
    plan = _plan()
    assert [m["title"] for m in plan["modules"]] == ["Fundamentos", "Estrutura"]
    assert plan["modules"][0]["status"] == "current"
    assert plan["modules"][0]["lessons"][0]["status"] == "current"
    assert plan["generated"] is True


def test_advancing_crosses_module_borders_and_marks_modules_done() -> None:
    plan = _plan()
    plan, pos = curriculum.advance_lesson(plan, curriculum.Position(0, 0))
    assert pos == curriculum.Position(0, 1)
    plan, pos = curriculum.skip_lesson(plan, pos)
    assert pos == curriculum.Position(1, 0)
    assert plan["modules"][0]["status"] == "done"
    assert plan["modules"][0]["lessons"][1]["status"] == "skipped"
    plan, pos = curriculum.advance_lesson(plan, pos)
    assert pos is None


def test_render_says_where_we_are_and_what_is_next_only() -> None:
    text = curriculum.render_plan(_plan(), curriculum.Position(0, 0))
    assert "Current lesson: O inconsciente" in text
    assert "Next: Recalque → Id" in text
    assert "vazio" not in text


def test_a_failed_plan_call_still_yields_a_teachable_plan() -> None:
    goal = fallback_goal("Quero aprender psicologia segundo Freud do zero.")
    assert goal.subject == "psicologia segundo Freud do zero"
    assert goal.inferred_level == "introductory"
    assert goal.parsed is False
    plan = curriculum.fallback_plan(goal)
    assert curriculum.concepts_of_current_lesson(plan, curriculum.Position(0, 0))


# ── memory ────────────────────────────────────────────────────────────────


def test_compaction_is_a_size_decision_and_never_below_keep() -> None:
    small = [_Turn("x" * 40) for _ in range(5)]
    assert not memory.should_compact(small, after_tokens=100, after_turns=24, keep=6)
    many = [_Turn("x" * 40) for _ in range(25)]
    assert memory.should_compact(many, after_tokens=100_000, after_turns=24, keep=6)
    big = [_Turn("x" * 4000) for _ in range(8)]
    assert memory.should_compact(big, after_tokens=4500, after_turns=24, keep=6)
    boundary = [_Turn("x" * 40) for _ in range(12)]
    assert memory.should_compact(
        boundary, after_tokens=100_000, after_turns=100, keep=6, boundary=True
    )


def test_validate_memory_dedupes_and_caps() -> None:
    out = memory.validate_memory(
        {
            "goal": " Freud ",
            "concepts_covered": ["a", "A", " a ", "b"],
            "questions_answered": 3.0,
            "junk": 1,
        }
    )
    assert out["goal"] == "Freud"
    assert out["concepts_covered"] == ["a", "b"]
    assert out["questions_answered"] == 3
    assert out["next_step"] == ""


def test_profile_merge_dedupes_and_keeps_the_newest_six() -> None:
    profile = {"patterns": [f"p{i}" for i in range(5)]}
    merged = memory.merge_profile(profile, {"learner_patterns": ["p4", "p5", "p6"]})
    assert merged["patterns"] == ["p1", "p2", "p3", "p4", "p5", "p6"]
    assert profile["patterns"] == [f"p{i}" for i in range(5)]  # not mutated


# ── assessment ────────────────────────────────────────────────────────────


def test_parse_questions_keeps_only_gradeable_ones() -> None:
    questions = assessment.parse_questions(
        {
            "questions": [
                {
                    "type": "mcq",
                    "prompt": "?",
                    "concept": "c",
                    "options": ["a"],
                    "correct_index": 0,
                },
                {
                    "type": "mcq",
                    "prompt": "?",
                    "concept": "c",
                    "options": ["a", "b"],
                    "correct_index": 1,
                },
                {"type": "true_false", "prompt": "?", "concept": "c", "answer": "yes"},
                {"type": "short", "prompt": "?", "concept": "c", "accepted": ["x"]},
                {"type": "ordering", "prompt": "?", "concept": "c", "order": ["1", "2"]},
                {"type": "open", "prompt": "?", "concept": "c", "rubric": ["r"]},
            ]
        },
        limit=6,
    )
    assert [q["type"] for q in questions] == ["mcq", "short", "open"]


def test_closed_types_grade_deterministically_and_open_ones_defer() -> None:
    assert assessment.grade({"type": "mcq", "correct_index": 1}, 1) == (1.0, True)
    assert assessment.grade({"type": "true_false", "answer": False}, False) == (1.0, True)
    assert assessment.grade({"type": "short", "accepted": ["Recalque"]}, "recalque") == (
        1.0,
        True,
    )
    score, correct = assessment.grade(
        {"type": "ordering", "order": ["a", "b", "c"]}, ["a", "c", "b"]
    )
    assert 0 < score < 1 and not correct
    assert assessment.grade({"type": "open", "rubric": ["r"]}, "text") == (-1.0, False)


def test_the_public_paper_carries_no_answers() -> None:
    class Row:
        id = "00000000-0000-0000-0000-000000000001"
        kind = "micro"
        status = "open"
        title = "t"
        score = None
        results: ClassVar[dict[str, Any]] = {}
        questions: ClassVar[list[dict[str, Any]]] = [
            {
                "type": "mcq",
                "prompt": "?",
                "concept": "c",
                "options": ["a", "b"],
                "correct_index": 1,
            },
            {"type": "ordering", "prompt": "?", "concept": "c", "order": ["b", "a", "c"]},
            {"type": "open", "prompt": "?", "concept": "c", "rubric": ["secret"]},
        ]

    view = assessment.public_view(Row())  # type: ignore[arg-type]
    dumped = str(view)
    assert (
        "correct_index" not in dumped
        and "rubric" not in dumped
        and "secret" not in dumped
    )
    assert view["questions"][1]["items"] == ["a", "b", "c"]
