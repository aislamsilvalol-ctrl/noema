"""The token budget of one teaching turn, and the report of what was spent.

Not "as little as possible" — as much as teaches, no more. Each component of
the prompt gets an allowance; the transcript is fitted newest-first inside
its own; what did not fit is what the summaries are for. The estimate is the
codebase's own (`chars ÷ 4`, `retrieval/grounding.py`), used consistently so
before/after comparisons compare like with like.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

__all__ = [
    "CHARS_PER_TOKEN",
    "ContextReport",
    "TokenBudget",
    "estimate",
    "fit_transcript",
]

CHARS_PER_TOKEN = 4


def estimate(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


@dataclass(frozen=True, slots=True)
class TokenBudget:
    #: Stored transcript that rides verbatim (L0).
    transcript: int = 3_500
    #: Session/module summaries (L1/L2).
    memory: int = 900
    #: Knowledge state + profile (L3/L4).
    student: int = 600
    #: Retrieved material, when a notebook has some.
    materials: int = 6_000
    #: The reply itself.
    response: int = 1_400


class _Turn(Protocol):
    content: str
    token_estimate: int


@dataclass
class ContextReport:
    """Tokens per component, estimated the same way everywhere."""

    system: int = 0
    transcript: int = 0
    transcript_turns: int = 0
    transcript_dropped: int = 0
    memory: int = 0
    student: int = 0
    session: int = 0
    materials: int = 0
    message: int = 0
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return (
            self.system
            + self.transcript
            + self.memory
            + self.student
            + self.session
            + self.materials
            + self.message
        )

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["total"] = self.total
        return data


def fit_transcript[T: _Turn](turns: Sequence[T], budget: int) -> tuple[list[T], int]:
    """The newest turns that fit in `budget`, in chronological order, and how
    many were left out. The newest turn always rides, whatever it costs — a
    reply to a message the model did not see is not a reply."""
    kept: list[T] = []
    used = 0
    for turn in reversed(turns):
        cost = turn.token_estimate or estimate(turn.content)
        if kept and used + cost > budget:
            break
        kept.append(turn)
        used += cost
    kept.reverse()
    return kept, len(turns) - len(kept)
