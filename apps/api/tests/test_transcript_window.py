"""What history rides in a call: `/ai/chat`'s trim and the Professor's
cache-friendly transcript window."""

from __future__ import annotations

from dataclasses import dataclass

from noema.api.v1.ai import trim_history
from noema.api.v1.schemas import ChatMessageIn
from noema.professor.budget import fit_transcript, fit_transcript_stable
from noema.providers.base import Role


@dataclass
class Turn:
    content: str
    token_estimate: int


def test_chat_history_keeps_the_newest_messages_that_fit() -> None:
    sent = [
        ChatMessageIn(role="user", content="a" * 32_000),
        ChatMessageIn(role="assistant", content="b" * 400),
        ChatMessageIn(role="user", content="c" * 400),
        ChatMessageIn(role="assistant", content="d" * 400),
        ChatMessageIn(role="user", content="question"),
    ]

    kept = trim_history(sent, budget=500)

    # The 8K-token opener is dropped; the history starts on a learner's message.
    assert [m.content[0] for m in kept] == ["c", "d", "q"]
    assert kept[0].role is Role.USER


def test_chat_history_always_keeps_the_question() -> None:
    kept = trim_history([ChatMessageIn(role="user", content="x" * 32_000)], budget=10)

    assert len(kept) == 1


def test_the_stable_window_moves_in_steps() -> None:
    turns = [Turn(f"t{i}", 100) for i in range(20)]

    exact, dropped = fit_transcript(turns, 1_000)
    stable, start = fit_transcript_stable(turns, 1_000, step=6)

    assert dropped == 10
    assert start == 6  # held at a multiple of the step
    assert stable[0].content == "t6"
    assert len(stable) == 14 and len(exact) == 10


def test_the_stable_window_starts_in_the_same_place_turn_after_turn() -> None:
    starts = []
    for n in range(14, 20):
        _, start = fit_transcript_stable(
            [Turn("t", 100) for _ in range(n)], 1_000, step=6
        )
        starts.append(start)

    # The start moves once, by a whole step, then holds while turns arrive.
    assert starts == [0, 0, 6, 6, 6, 6]


def test_the_stable_window_never_runs_past_its_slack() -> None:
    turns = [Turn("t", 100) for _ in range(30)]

    kept, _ = fit_transcript_stable(turns, 1_000, step=12, slack=1.2)

    assert sum(t.token_estimate for t in kept) <= 1_200
