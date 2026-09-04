"""The pedagogy record never reaches the learner, and only valid fields survive."""

from __future__ import annotations

from noema.services.teaching_policy import SidecarFilter, parse_pedagogy, principles


def run(chunks: list[str]) -> tuple[str, str]:
    f = SidecarFilter()
    shown = "".join(f.feed(c) for c in chunks) + f.flush()
    return shown, f.record


def test_record_is_split_from_the_reply_even_across_chunks() -> None:
    shown, record = run(
        [
            "Start with the slip. ",
            "Now: which part did the work?\n<PEDA",
            'GOGY>{"a":',
            " 1}</PEDAGOGY>",
        ]
    )
    assert shown == "Start with the slip. Now: which part did the work?\n"
    assert record == '{"a": 1}</PEDAGOGY>'


def test_a_stray_angle_bracket_is_delayed_not_lost() -> None:
    shown, record = run(["a < b", " and b <", " c"])
    assert shown == "a < b and b < c"
    assert record == ""


def test_partial_marker_at_the_end_is_released_on_flush() -> None:
    shown, _ = run(["fine <PEDA"])
    assert shown == "fine <PEDA"


def test_parse_keeps_only_valid_fields() -> None:
    raw = (
        '{"subject": "Freud", "current_concept": "the unconscious",'
        ' "learner_level": "beginner", "depth": "foundational",'
        ' "strategy": "analogy", "situation": "confused",'
        ' "next_action": "check", "misconception": null,'
        ' "mastery_evidence": {"concept": "repression", "verdict": "partial",'
        ' "strength": "loud"},'
        ' "plan": [{"topic": "id/ego/superego", "status": "current"}, {"topic": 3}],'
        ' "surprise": "dropped"}</PEDAGOGY>'
    )
    parsed = parse_pedagogy(raw)
    assert parsed == {
        "subject": "Freud",
        "current_concept": "the unconscious",
        "depth": "foundational",
        "strategy": "analogy",
        "situation": "confused",
        "next_action": "check",
        "mastery_evidence": {
            "concept": "repression",
            "verdict": "partial",
            "strength": "weak",
        },
        "plan": [{"topic": "id/ego/superego", "status": "current"}],
    }


def test_unknown_verdict_is_not_evidence() -> None:
    parsed = parse_pedagogy(
        '{"mastery_evidence": {"concept": "x", "verdict": "unknown"}}'
    )
    assert parsed is None


def test_garbage_is_no_record() -> None:
    assert parse_pedagogy("") is None
    assert parse_pedagogy("not json") is None
    assert parse_pedagogy("[1,2]") is None


def test_principles_prompt_loads_and_demands_the_record() -> None:
    prompt = principles()
    assert "<PEDAGOGY>" in prompt.body
    assert "END WITH ONE QUESTION" in prompt.body
