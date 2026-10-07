"""Concept review follows the cards' FSRS clock, and falls back to seven days.

The pure half. The database wiring — a real review writing ``due_at``, and a
draft being ignored — lives in ``test_db_concept_review.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from noema.engines import fsrs
from noema.professor.student import (
    REVIEW_AFTER,
    concept_review_due,
    current_stage,
    dues_for_concept,
    next_concept_review_at,
)

NOW = datetime(2026, 10, 7, 12, tzinfo=UTC)
LAST = datetime(2026, 10, 1, 12, tzinfo=UTC)


def _due_after(rating: fsrs.Rating) -> datetime:
    """The interval ``study.review`` would schedule, before its fuzz.

    First review, so ``next_state`` starts from nothing. The concept clock
    does not recompute this — it reads the ``due_at`` that call already
    stored — but the two states have to come from FSRS or the test is just
    comparing numbers it invented.
    """
    state = fsrs.next_state(None, rating, 0.0)
    return NOW + timedelta(days=fsrs.interval_days(state, 0.9))


def test_cards_in_different_fsrs_states_schedule_different_concept_reviews() -> None:
    hard = _due_after(fsrs.Rating.HARD)
    easy = _due_after(fsrs.Rating.EASY)
    assert hard != easy
    assert next_concept_review_at(LAST, (hard,)) == hard
    assert next_concept_review_at(LAST, (easy,)) == easy
    # Several cards, one concept: the earliest due, the same card the deck
    # would offer first.
    assert next_concept_review_at(LAST, (easy, hard)) == min(hard, easy)


def test_a_concept_without_cards_is_reviewed_after_seven_days() -> None:
    assert next_concept_review_at(LAST, ()) == LAST + REVIEW_AFTER
    assert timedelta(days=7) == REVIEW_AFTER
    # Exactly seven days is not yet due — the historical strict inequality.
    assert current_stage("mastered", LAST, now=LAST + REVIEW_AFTER) == "mastered"
    assert (
        current_stage("mastered", LAST, now=LAST + REVIEW_AFTER + timedelta(seconds=1))
        == "needs_review"
    )
    assert not concept_review_due(
        stage="mastered", last_evidence_at=LAST, now=LAST + REVIEW_AFTER
    )
    assert concept_review_due(
        stage="mastered",
        last_evidence_at=LAST,
        now=LAST + REVIEW_AFTER + timedelta(seconds=1),
    )


def test_an_overdue_card_reviews_the_concept_before_the_seven_days() -> None:
    """One day of silence used to leave a mastered concept alone. A card
    already due does not wait out the week."""
    yesterday = NOW - timedelta(days=1)
    due = NOW - timedelta(hours=1)
    assert current_stage("mastered", yesterday, now=NOW) == "mastered"
    assert (
        current_stage("mastered", yesterday, now=NOW, card_due_ats=(due,))
        == "needs_review"
    )
    assert concept_review_due(
        stage="mastered",
        last_evidence_at=yesterday,
        card_due_ats=(due,),
        now=NOW,
    )


def test_a_card_due_later_holds_the_concept_past_seven_days() -> None:
    """The lesson last touched this ten days ago. The card says the memory
    still holds, so the map does not ask for a review the deck is not asking
    for."""
    shown = NOW - timedelta(days=10)
    due = NOW + timedelta(days=20)
    assert current_stage("mastered", shown, now=NOW) == "needs_review"
    assert current_stage("mastered", shown, now=NOW, card_due_ats=(due,)) == "mastered"
    assert not concept_review_due(
        stage="mastered", last_evidence_at=shown, card_due_ats=(due,), now=NOW
    )


def test_a_concept_still_being_learned_is_not_aged_into_a_review() -> None:
    due = NOW - timedelta(days=1)
    assert current_stage("learning", LAST, now=NOW, card_due_ats=(due,)) == "learning"
    assert not concept_review_due(
        stage="learning", last_evidence_at=LAST, card_due_ats=(due,), now=NOW
    )


def test_a_review_already_asked_is_not_asked_again() -> None:
    due = NOW - timedelta(days=1)
    assert not concept_review_due(
        stage="mastered",
        last_evidence_at=LAST,
        notes=["reviewed"],
        card_due_ats=(due,),
        now=NOW,
    )


def test_name_only_cards_and_graph_cards_share_one_earliest_due() -> None:
    concept_id = uuid.uuid4()
    early = datetime(2026, 10, 2, tzinfo=UTC)
    late = datetime(2026, 12, 1, tzinfo=UTC)
    dues = dues_for_concept(
        concept_id=concept_id,
        normalized_name="cadeia",
        by_concept_id={concept_id: (late,)},
        by_name={"cadeia": (early,)},
    )
    assert next_concept_review_at(LAST, dues) == early
