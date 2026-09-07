"""The evidence log carries what a learner model reads, and leaves as pseudonyms.

Phase 0 of Aquilante on the product side: mastery events store the item,
the time to answer, the difficulty, the stated confidence, the session and
the graph's concept id when known; the concept state stamps the projection
version; the export turns reviews, answers and mastery events into one
stream with HMAC identities and no text.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import LearningJourney, MasteryEvent, User
from noema.professor.student import PROJECTION_VERSION, StudentModel
from noema.services.learning_export import (
    event_from_mastery,
    export_events,
    pseudonym,
    to_jsonl,
)

SECRET = "an-export-secret-of-decent-length"


async def _journey(db: AsyncSession, user: User) -> LearningJourney:
    journey = LearningJourney(
        owner_id=user.id,
        goal="Understand Freud",
        subject="Psychology",
        inferred_level="beginner",
        plan={"modules": []},
        profile={},
    )
    db.add(journey)
    await db.flush()
    return journey


async def test_record_stores_the_signals_and_stamps_the_projection(
    db: AsyncSession, user: User
) -> None:
    journey = await _journey(db, user)
    student = StudentModel(db, user.id, journey)
    session_id = uuid.uuid4()
    state = await student.record(
        "Unconscious",
        kind="quiz",
        score=0.0,
        detail={"question": "…"},
        item_id="quiz:abc123",
        elapsed_ms=14_200,
        difficulty=0.6,
        confidence=0.25,
        session_id=None,  # a FK: only real sessions may be referenced
    )
    assert state.model_version == PROJECTION_VERSION
    event = (
        await db.execute(
            select(MasteryEvent).where(MasteryEvent.journey_id == journey.id)
        )
    ).scalar_one()
    assert event.item_id == "quiz:abc123"
    assert event.elapsed_ms == 14_200
    assert event.difficulty == pytest.approx(0.6)
    assert event.confidence == pytest.approx(0.25)
    assert event.session_id is None and session_id  # unused id: the FK is what matters
    assert (
        event.concept_id == state.concept_id
    )  # None here; linked when the graph knows it


async def test_signals_are_clamped_and_optional(db: AsyncSession, user: User) -> None:
    journey = await _journey(db, user)
    student = StudentModel(db, user.id, journey)
    await student.record(
        "Ego", kind="check", score=1.0, elapsed_ms=-5, difficulty=1.7, confidence=-1
    )
    await student.record("Ego", kind="conversation", score=0.5)
    events = (
        (await db.execute(select(MasteryEvent).order_by(MasteryEvent.created_at)))
        .scalars()
        .all()
    )
    assert (
        events[0].elapsed_ms == 0
        and events[0].difficulty == 1.0
        and events[0].confidence == 0.0
    )
    assert events[1].item_id is None and events[1].elapsed_ms is None


async def test_export_is_pseudonymous_and_carries_no_text(
    db: AsyncSession, user: User
) -> None:
    journey = await _journey(db, user)
    student = StudentModel(db, user.id, journey)
    then = datetime.now(UTC) - timedelta(days=2)
    await student.record(
        "Superego",
        kind="quiz",
        score=1.0,
        detail={"question": "Which part did the work?", "chosen": "the superego"},
        item_id="quiz:deadbeef",
        elapsed_ms=9_000,
        now=then,
    )
    await student.record("Superego", kind="conversation", score=0.5, note="secret note")

    rows = [
        e async for e in export_events(db, secret=SECRET, since=then - timedelta(hours=1))
    ]
    mine = [r for r in rows if r["student_id"] == pseudonym(SECRET, user.id)]
    assert len(mine) == 2
    graded, exposure = mine
    assert graded["event_type"] == "answer" and graded["correct"] is True
    assert graded["item_id"] == "quiz:deadbeef" and graded["response_ms"] == 9_000
    assert exposure["event_type"] == "exposure" and exposure["correct"] is None
    for row in mine:
        line = to_jsonl(row)
        assert str(user.id) not in line and user.email not in line
        assert "Which part" not in line and "secret note" not in line
        assert json.loads(line)["schema_version"] == 1
    # the same secret gives the same pseudonym; another secret another population
    assert pseudonym(SECRET, user.id) == pseudonym(SECRET, user.id)
    assert pseudonym(SECRET, user.id) != pseudonym("another-secret-of-length-16", user.id)


async def test_export_refuses_a_weak_secret(db: AsyncSession) -> None:
    with pytest.raises(ValueError):
        async for _ in export_events(db, secret="short"):
            pass


def test_mastery_mapping_marks_unlinked_concepts_by_name() -> None:
    event = MasteryEvent(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        journey_id=uuid.uuid4(),
        concept_name="  Defense Mechanisms ",
        concept_id=None,
        kind="flashcard",
        score=0.85,
        weight=0.8,
        detail={},
        created_at=datetime.now(UTC),
        item_id="card:1",
        elapsed_ms=None,
        difficulty=None,
        confidence=None,
        session_id=None,
    )
    out = event_from_mastery(event, SECRET)
    assert out["concept_id"] == "name:defense mechanisms"
    assert out["correct"] is True and out["event_type"] == "answer"
