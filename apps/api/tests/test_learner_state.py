"""The single reading over both projections — pure, so it runs without a database."""

from __future__ import annotations

from datetime import UTC, datetime

from noema.engines.learner import (
    GraphReading,
    JourneyReading,
    Source,
    read,
)

EARLY = datetime(2026, 9, 1, tzinfo=UTC)
LATE = datetime(2026, 9, 20, tzinfo=UTC)


def test_a_concept_nobody_has_seen_has_no_number() -> None:
    """Silence is not zero mastery, and must not be rendered as one."""
    state = read()
    assert state.mastery is None
    assert state.source is Source.NONE
    assert state.provisional


def test_the_graph_answers_when_it_has_evidence() -> None:
    state = read(
        graph=GraphReading(mastery=72.5, uncertainty=0.04, evidence_count=9.0),
        journey=JourneyReading(score=0.6, stage="learning", evidence_count=3),
    )
    assert state.source is Source.GRAPH
    assert state.mastery == 72.5
    assert state.uncertainty == 0.04
    assert not state.provisional


def test_a_concept_met_only_in_conversation_is_answered_and_marked_provisional() -> None:
    """No cards and no answers means the graph has nothing to say — not that
    the learner knows nothing."""
    state = read(journey=JourneyReading(score=0.8, stage="learning", evidence_count=4))
    assert state.source is Source.JOURNEY
    assert state.mastery == 80.0
    assert state.provisional
    assert state.uncertainty is None


def test_thin_graph_evidence_stays_provisional() -> None:
    thin = read(graph=GraphReading(mastery=90.0, evidence_count=2.0))
    assert thin.source is Source.GRAPH
    assert thin.provisional
    thick = read(graph=GraphReading(mastery=90.0, evidence_count=4.0))
    assert not thick.provisional


def test_the_two_halves_disagreeing_is_reported_not_averaged() -> None:
    """The seam this reader exists to make visible."""
    state = read(
        graph=GraphReading(mastery=40.0, evidence_count=6.0),
        journey=JourneyReading(score=0.9, stage="mastered", evidence_count=5),
    )
    assert state.mastery == 40.0  # the graph is the projection of record
    assert state.disagreement == 50.0
    # An average would have invented 65, which neither projection believes.
    assert state.mastery != 65.0


def test_one_projection_alone_cannot_disagree_with_itself() -> None:
    assert read(graph=GraphReading(mastery=40.0, evidence_count=6.0)).disagreement is None
    assert read(journey=JourneyReading(score=0.4, evidence_count=2)).disagreement is None


def test_the_reading_carries_the_lessons_own_findings() -> None:
    """Stage and misconceptions live on the journey side; the graph has neither."""
    state = read(
        graph=GraphReading(mastery=55.0, evidence_count=8.0),
        journey=JourneyReading(
            score=0.5,
            stage="needs_review",
            evidence_count=4,
            strong_evidence_count=2,
            misconceptions=("thinks recursion is a loop",),
        ),
    )
    assert state.stage == "needs_review"
    assert state.misconceptions == ("thinks recursion is a loop",)
    assert state.strong_evidence_count == 2


def test_the_latest_evidence_wins_whichever_side_it_came_from() -> None:
    state = read(
        graph=GraphReading(mastery=50.0, evidence_count=5.0, last_evidence_at=EARLY),
        journey=JourneyReading(score=0.5, evidence_count=2, last_evidence_at=LATE),
    )
    assert state.last_evidence_at == LATE


def test_both_readings_are_kept_so_a_caller_can_see_the_working() -> None:
    graph = GraphReading(mastery=50.0, evidence_count=5.0)
    journey = JourneyReading(score=0.5, evidence_count=2)
    state = read(graph=graph, journey=journey)
    assert state.graph is graph
    assert state.journey is journey
