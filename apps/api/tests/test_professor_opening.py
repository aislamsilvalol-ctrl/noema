"""First contact and the last gate: the professor asks before teaching, and
internal context never reaches the learner."""

from __future__ import annotations

import pytest

from noema.professor import moves
from noema.professor.leaks import LeakFilter


@pytest.mark.parametrize(
    "opening",
    [
        "Quero aprender Python.",
        "I want to learn Italian.",
        "Quiero aprender filosofía.",
        "como vacinas funcionam",
    ],
)
def test_an_opening_without_a_level_says_nothing_about_one(opening: str) -> None:
    assert not moves.states_level(opening)


@pytest.mark.parametrize(
    "opening",
    [
        "Quero aprender Python do zero.",
        "Já programo em Java e quero aprender Python.",
        "I want to learn Italian from scratch.",
        "I already know the basics of chess.",
        "Quiero aprender alemán, ya sé lo básico.",
    ],
)
def test_an_opening_that_states_a_level(opening: str) -> None:
    assert moves.states_level(opening)


def test_first_contact_without_a_level_asks_before_teaching() -> None:
    d = moves.decide(
        moves.Signal.NEUTRAL, moves.Situation(first_turn=True, level_known=False)
    )
    assert d.move is moves.Move.DIAGNOSE
    assert not d.require_check
    assert d.mino == "curious"
    assert d.intent == "diagnose"


def test_first_contact_with_a_level_teaches_as_before() -> None:
    d = moves.decide(
        moves.Signal.NEUTRAL, moves.Situation(first_turn=True, level_known=True)
    )
    assert d.move is moves.Move.TEACH


def test_a_first_question_is_still_answered() -> None:
    d = moves.decide(
        moves.Signal.ASKS, moves.Situation(first_turn=True, level_known=False)
    )
    assert d.move is moves.Move.ANSWER


@pytest.mark.parametrize(
    "signal",
    [
        moves.Signal.NEUTRAL,
        moves.Signal.ANSWERING,
        moves.Signal.KNOWS,
        moves.Signal.CONFUSED,
    ],
)
def test_the_answer_to_the_opening_question_starts_the_lesson(
    signal: moves.Signal,
) -> None:
    d = moves.decide(signal, moves.Situation(last_move=moves.Move.DIAGNOSE.value))
    assert d.move is moves.Move.TEACH
    assert d.require_check


def test_a_question_back_after_the_opening_is_answered() -> None:
    d = moves.decide(
        moves.Signal.ASKS, moves.Situation(last_move=moves.Move.DIAGNOSE.value)
    )
    assert d.move is moves.Move.ANSWER


def _run(chunks: list[str]) -> tuple[str, LeakFilter]:
    f = LeakFilter()
    out = "".join(f.feed(c) for c in chunks) + f.flush()
    return out, f


def test_prose_passes_untouched() -> None:
    text = "Se x < 3 e y > 2, então <b> não é tag nossa. Fim."
    out, f = _run([text[:9], text[9:20], text[20:]])
    assert out == text
    assert f.dropped == 0


def test_an_echoed_section_is_removed_even_split_across_chunks() -> None:
    chunks = [
        "Boa. <KNOWLEDGE",
        "_STATE>\nconcept: Bhaskara mastery=0.4\n</KNOWLEDGE_",
        "STATE> Vamos lá.",
    ]
    out, f = _run(chunks)
    assert out == "Boa.  Vamos lá."
    assert "mastery" not in out
    assert f.dropped > 0


def test_an_unclosed_section_stays_hidden() -> None:
    out, _ = _run(["Certo.\n<TURN_DIRECTIVE>\nTHIS TURN: TEACH. One idea"])
    assert out == "Certo.\n"


def test_a_stray_closing_tag_is_removed() -> None:
    out, _ = _run(["Pronto.</COURSE> Próximo passo."])
    assert out == "Pronto. Próximo passo."


def test_a_held_tail_that_is_not_a_tag_is_released() -> None:
    out, _ = _run(["a <CO", "OL> b"])
    assert out == "a <COOL> b"
    out, _ = _run(["termina com <CO"])
    assert out == "termina com <CO"
