"""The move router reads unified mastery, not the journey score alone.

`engines.learner.read` is the reading of record: the graph's 0-100 number
when the graph has evidence, otherwise the journey score times 100. The
router used to be told only the journey stage and a boolean computed from
`StudentConceptState.score`. These tests are the cases where those two
disagree.
"""

from __future__ import annotations

from noema.db.models import ConceptState
from noema.engines.learner import GraphReading, JourneyReading, Source, read
from noema.professor import moves


def test_the_router_reviews_when_unified_mastery_falls_below_mastered() -> None:
    """The journey still says mastered (score 0.9). The graph, which is the
    reading of record, is at 40. The old router never saw that number and
    would keep teaching."""
    faded = read(
        graph=GraphReading(mastery=40.0, evidence_count=6.0, retrievability=0.2),
        journey=JourneyReading(
            score=0.9,
            stage=ConceptState.MASTERED.value,
            evidence_count=5,
            strong_evidence_count=2,
        ),
    )
    assert faded.source is Source.GRAPH
    assert faded.mastery == 40.0
    decision = moves.decide(
        moves.Signal.NEUTRAL,
        moves.Situation(
            last_move="teach",
            knowledge=(moves.ConceptKnowledge(name="lapso", learner=faded),),
        ),
    )
    assert decision.move is moves.Move.REVIEW
    assert decision.remediation == ("lapso",)
    assert decision.mino == "reviewing"

    holding = read(
        graph=GraphReading(mastery=88.0, evidence_count=6.0, retrievability=0.95),
        journey=JourneyReading(
            score=0.9,
            stage=ConceptState.MASTERED.value,
            evidence_count=5,
            strong_evidence_count=2,
        ),
    )
    kept = moves.decide(
        moves.Signal.NEUTRAL,
        moves.Situation(
            last_move="teach",
            knowledge=(moves.ConceptKnowledge(name="lapso", learner=holding),),
        ),
    )
    assert kept.move is moves.Move.TEACH


def test_a_journey_only_mastered_concept_is_not_reviewed_by_the_new_rule() -> None:
    """No graph: the unified number is the journey score times 100, already
    at or above the mastered bar. The seven-day / FSRS clock still decides,
    through ``review_due``, and this rule adds nothing."""
    journey_only = read(
        journey=JourneyReading(
            score=0.9,
            stage=ConceptState.MASTERED.value,
            evidence_count=5,
            strong_evidence_count=2,
        )
    )
    assert journey_only.source is Source.JOURNEY
    assert journey_only.mastery == 90.0
    assert not moves.memory_dropped(journey_only)
    decision = moves.decide(
        moves.Signal.NEUTRAL,
        moves.Situation(
            last_move="teach",
            knowledge=(moves.ConceptKnowledge(name="lapso", learner=journey_only),),
        ),
    )
    assert decision.move is moves.Move.TEACH


def test_a_thin_graph_does_not_pull_the_lesson_into_review() -> None:
    thin = read(
        graph=GraphReading(mastery=30.0, evidence_count=2.0),
        journey=JourneyReading(
            score=0.9, stage=ConceptState.MASTERED.value, evidence_count=4
        ),
    )
    assert thin.provisional
    assert not moves.memory_dropped(thin)


def test_teach_back_uses_the_unified_scale_not_the_journey_score() -> None:
    """0.6 on the journey scale is 60 on the unified one. A graph at 40
    overrides a journey score of 0.9; a graph at 85 teaches back even when
    the journey score is 0.4."""
    assert moves.TEACH_BACK_MASTERY == 60.0
    assert moves.MASTERED_MASTERY == 80.0

    low = read(
        graph=GraphReading(mastery=40.0, evidence_count=6.0),
        journey=JourneyReading(
            score=0.9,
            stage="mastered",
            evidence_count=4,
            strong_evidence_count=2,
        ),
    )
    assert low.mastery == 40.0
    skipped = moves.decide(
        moves.Signal.NEUTRAL,
        moves.Situation(since_check=3, teach_back_due=True, focus_learner=low),
    )
    assert skipped.move is moves.Move.QUESTION
    assert skipped.extras == {}

    high = read(
        graph=GraphReading(mastery=85.0, evidence_count=6.0),
        journey=JourneyReading(
            score=0.4,
            stage="learning",
            evidence_count=4,
            strong_evidence_count=2,
        ),
    )
    assert high.mastery == 85.0
    asked = moves.decide(
        moves.Signal.NEUTRAL,
        moves.Situation(since_check=3, teach_back_due=True, focus_learner=high),
    )
    assert asked.extras == {"teach_back": True}


def test_teach_back_bar_is_the_old_point_six_when_only_the_journey_spoke() -> None:
    at_bar = read(
        journey=JourneyReading(
            score=0.6, stage="learning", evidence_count=3, strong_evidence_count=2
        )
    )
    below = read(
        journey=JourneyReading(
            score=0.59, stage="learning", evidence_count=3, strong_evidence_count=2
        )
    )
    assert at_bar.mastery == 60.0
    assert below.mastery == 59.0
    asked = moves.decide(
        moves.Signal.NEUTRAL,
        moves.Situation(since_check=3, teach_back_due=True, focus_learner=at_bar),
    )
    assert asked.extras == {"teach_back": True}
    skipped = moves.decide(
        moves.Signal.NEUTRAL,
        moves.Situation(since_check=3, teach_back_due=True, focus_learner=below),
    )
    assert skipped.extras == {}
