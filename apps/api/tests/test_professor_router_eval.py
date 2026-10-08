"""The Professor eval's scripted turns, checked against the router alone.

The live eval (`scripts/eval_professor.py`) costs money and needs a model.
This is its free half: for every scripted learner message, the regexes must
read the signal the scenario says they read (or stay out of it, when the
classifier is meant to decide), and `decide()` must choose the expected move
in the stated situation. A change to `_PATTERNS` or to a rule in `decide()`
that breaks "não entendi", "me guia" or "tô cansado" fails here, in CI,
before anyone pays for a run.
"""

from __future__ import annotations

import pytest

from noema.evals import professor as evals
from noema.professor.moves import (
    Signal,
    Situation,
    decide,
    read_signal,
    requested_strategy,
)

CASES = evals.router_cases()


def test_the_scenarios_cover_what_the_eval_promises() -> None:
    scenarios = evals.load_scenarios()["scenarios"]
    assert 12 <= len(scenarios) <= 16
    assert {s["language"] for s in scenarios} >= {"pt", "es"}
    assert any(len(s["turns"]) >= 8 for s in scenarios)
    assert all(t.get("router") for s in scenarios for t in s["turns"])


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_the_router_reads_each_scripted_turn(case: evals.RouterCase) -> None:
    read = read_signal(case.text)
    if case.via == "pattern":
        assert read.value == case.signal, f"{case.text!r} read as {read.value}"
    elif case.via in ("classifier", "awaiting", "first_turn"):
        # A regex that fires here would take the decision away from the
        # classifier (or from "a question is open") — a false positive.
        assert read is Signal.NEUTRAL, f"{case.text!r} caught by a pattern: {read.value}"

    situation = Situation(
        **case.situation,
        requested_strategy=requested_strategy(case.text),
    )
    decision = decide(Signal(case.signal), situation)
    assert decision.move.value in case.moves, (
        f"{case.signal} in {case.situation} → {decision.move.value} ({decision.reason})"
    )
    if case.strategy:
        assert decision.strategy == case.strategy


def test_language_heuristic() -> None:
    assert evals.detect_language("Você não precisa decorar isso: é só uma caixa.") == "pt"
    assert (
        evals.detect_language("The mitochondria is where the cell makes its energy.")
        == "en"
    )
    assert (
        evals.detect_language("No te preocupes, el pasado simple es para lo que ya pasó.")
        == "es"
    )
    assert evals.detect_language("ok") == ""


def test_checks_catch_sim_misuse_steps_and_a_given_away_answer() -> None:
    turn = evals.TurnResult(
        index=2,
        learner="E a de x³?",
        reply="Sim, a derivada de x³ é 3x². Quer tentar a de x⁴?",
        move="answer",
    )
    checks = {
        c.name: c.passed
        for c in evals.check_turn(
            {
                "moves": ["answer"],
                "opens_with_yes": False,
                "first_sentence_contains": ["3x²"],
                "ends_with_question": True,
                "not_regex": [r"(?<![\d.,])12(?![\d.,%])"],
            },
            turn,
        )
    }
    assert checks == {
        "move": True,
        "length": True,
        "sim": False,
        "ends_with_question": True,
        "answer_first": True,
        "forbidden": True,
    }

    steps = evals.TurnResult(index=1, learner="", reply="1. Isole x.\n2. Divida.\nPronto")
    assert evals.check_turn({"numbered_steps": True}, steps)[-1].passed


def test_repetition_is_flagged() -> None:
    reply = "A média é a soma de todos os valores dividida pela quantidade de valores."
    turn = evals.TurnResult(index=3, learner="", reply=reply)
    checks = evals.check_turn({}, turn, earlier=[reply])
    assert any(c.name == "repetition" and not c.passed for c in checks)


def test_a_term_defined_again_in_new_words_is_flagged() -> None:
    """The 2026-10-07 long session defined **estatística** four times."""
    first = "**Estatística** é a ciência que coleta e interpreta dados."
    again = evals.TurnResult(
        index=2,
        learner="Ok, pode continuar.",
        reply="Com os números 5, 7 e 3: **Estatística** é exatamente isso, dar sentido.",
        move="teach",
    )
    assert any(
        c.name == "redefinition" for c in evals.check_turn({}, again, earlier=[first])
    )
    example = evals.TurnResult(
        index=3,
        learner="Me dá um exemplo.",
        reply="Ontem fui ao mercado: aqui uso a **estatística** para comparar preços.",
        move="example",
    )
    assert not any(
        c.name == "redefinition" for c in evals.check_turn({}, example, earlier=[first])
    )
