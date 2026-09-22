"""One reading of what a learner knows about one concept.

NOEMA computes this twice. `engines/mastery.py` scores a concept from graded
evidence — a Beta posterior over weighted answers, multiplied by FSRS
retrievability — and stores it per `concepts.id`. `professor/student.py` scores
the same concept from what a lesson showed — a recency-weighted mean of
showings — and stores it per journey, by name. Since the two halves learned to
share concept ids they describe the same thing, and until something reads them
together they still answer separately.

This is that reading, and it is deliberately **not an average**. The graph
projection is the one of record: it is calibrated, it carries its own
uncertainty, and it knows about forgetting. The journey projection is evidence
the graph may not have yet — a concept met only in conversation has no cards and
no answers, so the graph has nothing to say about it. So the graph answers when
it has evidence, the journey answers when the graph is silent, and when both
speak the disagreement is reported rather than smoothed away. Averaging two
differently calibrated numbers would invent a third that neither side believes.

Pure: dataclasses in, a dataclass out. No session, no clock, no I/O — which is
what lets it be tested against fixtures rather than a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

__all__ = [
    "THIN_EVIDENCE",
    "GraphReading",
    "JourneyReading",
    "LearnerState",
    "Source",
    "read",
]

#: Below this many effective observations the graph's number is a guess wearing
#: a measurement's clothes. It is the mastery engine's own pseudo-count, so the
#: two agree about when a score is too thin to assert.
THIN_EVIDENCE = 4.0


@dataclass(frozen=True, slots=True)
class GraphReading:
    """A `concept_mastery` row, as values."""

    #: 0-100, competence times retrievability.
    mastery: float
    competence: float = 0.0
    retrievability: float = 0.0
    #: The posterior's own spread. Not the inverse of confidence; its width.
    uncertainty: float = 0.0
    #: Positive means the learner claims more than they show.
    calibration: float = 0.0
    #: Effective observations: weighted, so fractional on purpose.
    evidence_count: float = 0.0
    last_evidence_at: datetime | None = None
    model_version: int = 0


@dataclass(frozen=True, slots=True)
class JourneyReading:
    """A `student_concept_states` row, as values."""

    #: 0-1, a recency-weighted mean of what the lesson saw.
    score: float
    #: The stage the learner is shown: introduced, learning, mastered…
    stage: str = ""
    #: A plain count of showings, not the graph's weighted one.
    evidence_count: int = 0
    #: Showings that were not the professor reading its own conversation.
    strong_evidence_count: int = 0
    misconceptions: tuple[str, ...] = ()
    last_evidence_at: datetime | None = None
    model_version: str = ""


class Source(StrEnum):
    """Which projection answered."""

    GRAPH = "graph"
    JOURNEY = "journey"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class LearnerState:
    """What this learner knows about this concept, and who says so."""

    #: 0-100, or None when neither projection has seen anything.
    mastery: float | None
    source: Source
    #: True when the answer should be shown as a range, or not as a number.
    provisional: bool
    #: The answering projection's own spread, when it has one.
    uncertainty: float | None
    #: abs(graph - journey) on the 0-100 scale, when both spoke. The number worth
    #: watching: it is the seam this whole reader exists to make visible.
    disagreement: float | None
    #: The answering projection's count, in its own units — the graph's is
    #: weighted and fractional, the journey's is a plain tally, and adding them
    #: would produce a number that means nothing.
    evidence_count: float
    strong_evidence_count: int
    stage: str | None
    misconceptions: tuple[str, ...]
    last_evidence_at: datetime | None
    graph: GraphReading | None
    journey: JourneyReading | None


def read(
    graph: GraphReading | None = None, journey: JourneyReading | None = None
) -> LearnerState:
    """Merge both projections into one answer that still shows its working."""
    graph_speaks = graph is not None and graph.evidence_count > 0
    journey_speaks = journey is not None and journey.evidence_count > 0

    disagreement = None
    if graph_speaks and journey_speaks:
        assert graph is not None and journey is not None
        disagreement = round(abs(graph.mastery - journey.score * 100), 4)

    misconceptions = tuple(journey.misconceptions) if journey else ()
    stage = journey.stage or None if journey else None
    last_seen = _latest(
        graph.last_evidence_at if graph else None,
        journey.last_evidence_at if journey else None,
    )

    if graph_speaks:
        assert graph is not None
        return LearnerState(
            mastery=round(graph.mastery, 4),
            source=Source.GRAPH,
            provisional=graph.evidence_count < THIN_EVIDENCE,
            uncertainty=graph.uncertainty,
            disagreement=disagreement,
            evidence_count=graph.evidence_count,
            strong_evidence_count=journey.strong_evidence_count if journey else 0,
            stage=stage,
            misconceptions=misconceptions,
            last_evidence_at=last_seen,
            graph=graph,
            journey=journey,
        )

    if journey_speaks:
        assert journey is not None
        # A concept the graph has never scored: no cards, no answers, only a
        # lesson. Always provisional — the heaviest evidence here is still a
        # projection of showings, and the lightest is the professor reading its
        # own conversation.
        return LearnerState(
            mastery=round(journey.score * 100, 4),
            source=Source.JOURNEY,
            provisional=True,
            uncertainty=None,
            disagreement=disagreement,
            evidence_count=float(journey.evidence_count),
            strong_evidence_count=journey.strong_evidence_count,
            stage=stage,
            misconceptions=misconceptions,
            last_evidence_at=last_seen,
            graph=graph,
            journey=journey,
        )

    return LearnerState(
        mastery=None,
        source=Source.NONE,
        provisional=True,
        uncertainty=None,
        disagreement=None,
        evidence_count=0.0,
        strong_evidence_count=0,
        stage=stage,
        misconceptions=misconceptions,
        last_evidence_at=last_seen,
        graph=graph,
        journey=journey,
    )


def _latest(left: datetime | None, right: datetime | None) -> datetime | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)
