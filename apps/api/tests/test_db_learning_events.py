"""Lesson lifecycle facts: written once, however many times they are reported."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.base import utcnow
from noema.db.models import LearningJourney, LearningLifecycleEvent, User
from noema.db.repository import OwnedRepository
from noema.services import learning_events
from noema.services.learning_events import (
    LESSON_COMPLETED,
    LESSON_STARTED,
    SESSION_ABANDONED,
)
from noema.services.teaching_session import TeachingSessions

PLAN = {
    "modules": [
        {
            "title": "Limits",
            "status": "done",
            "lessons": [
                {"title": "Intuition", "status": "done", "concepts": ["limit"]},
                {"title": "Epsilon-delta", "status": "skipped", "concepts": ["eps"]},
            ],
        },
        {
            "title": "Derivatives",
            "status": "current",
            "lessons": [
                {"title": "Slope", "status": "done", "concepts": ["slope"]},
                {"title": "Rules", "status": "current", "concepts": ["rules"]},
            ],
        },
    ]
}


async def count(db: AsyncSession, owner: User, kind: str) -> int:
    return int(
        await db.scalar(
            select(func.count())
            .select_from(LearningLifecycleEvent)
            .where(
                LearningLifecycleEvent.owner_id == owner.id,
                LearningLifecycleEvent.kind == kind,
            )
        )
        or 0
    )


async def test_a_double_submit_records_one_row(db: AsyncSession, user: User) -> None:
    for _ in range(2):
        await learning_events.record(
            db, owner_id=user.id, kind=LESSON_STARTED, source_id="same-source"
        )
    assert await count(db, user, LESSON_STARTED) == 1


async def test_the_same_source_for_two_learners_is_two_facts(
    db: AsyncSession, user: User, other_user: User
) -> None:
    for owner in (user, other_user):
        assert await learning_events.record(
            db, owner_id=owner.id, kind=LESSON_STARTED, source_id="shared"
        )
    assert await count(db, user, LESSON_STARTED) == 1
    assert await count(db, other_user, LESSON_STARTED) == 1


async def test_the_first_learner_turn_starts_the_lesson_once(
    db: AsyncSession, user: User
) -> None:
    sessions = TeachingSessions(db, user.id)
    resumed = await sessions.start_or_resume(
        session_id=None, notebook_id=None, learning_goal="derivatives"
    )
    await sessions.record_learner(resumed.session, "teach me derivatives")
    await sessions.record_learner(resumed.session, "and the chain rule")
    # A retried first turn (same session, reported again) is still one fact.
    assert not await learning_events.lesson_started(db, resumed.session)

    rows = list(
        await db.scalars(
            select(LearningLifecycleEvent).where(
                LearningLifecycleEvent.owner_id == user.id
            )
        )
    )
    assert [(r.kind, r.session_id) for r in rows] == [
        (LESSON_STARTED, resumed.session.id)
    ]


async def test_done_lessons_are_completed_once_and_skips_are_not(
    db: AsyncSession, user: User
) -> None:
    journey = await OwnedRepository(db, LearningJourney, user.id).create(
        goal="calculus", plan=PLAN
    )
    assert await learning_events.sync_lesson_completions(db, journey) == 2
    assert await learning_events.sync_lesson_completions(db, journey) == 0

    rows = list(
        await db.scalars(
            select(LearningLifecycleEvent)
            .where(
                LearningLifecycleEvent.owner_id == user.id,
                LearningLifecycleEvent.kind == LESSON_COMPLETED,
            )
            .order_by(LearningLifecycleEvent.source_id)
        )
    )
    assert sorted(r.payload["title"] for r in rows) == ["Intuition", "Slope"]
    assert all(r.journey_id == journey.id for r in rows)


async def test_after_a_turn_reads_the_sessions_journey(
    db: AsyncSession, user: User, other_user: User
) -> None:
    journey = await OwnedRepository(db, LearningJourney, user.id).create(
        goal="calculus", plan=PLAN
    )
    sessions = TeachingSessions(db, user.id)
    session = (
        await sessions.start_or_resume(
            session_id=None, notebook_id=None, learning_goal="x"
        )
    ).session
    session.journey_id = journey.id
    await db.flush()

    # Someone else naming this session finds nothing to record.
    assert await learning_events.after_professor_turn(db, other_user.id, session.id) == 0
    assert await learning_events.after_professor_turn(db, user.id, session.id) == 2
    assert await learning_events.after_professor_turn(db, user.id, session.id) == 0


async def test_an_idle_session_is_abandoned_once_per_idle_spell(
    db: AsyncSession, user: User, other_user: User
) -> None:
    sessions = TeachingSessions(db, user.id)
    session = (
        await sessions.start_or_resume(
            session_id=None, notebook_id=None, learning_goal="x"
        )
    ).session
    session.last_turn_at = utcnow() - timedelta(hours=30)
    others = TeachingSessions(db, other_user.id)
    theirs = (
        await others.start_or_resume(session_id=None, notebook_id=None, learning_goal="y")
    ).session
    theirs.last_turn_at = utcnow() - timedelta(hours=30)
    await db.flush()

    # Scoped to one learner: the other's idle lesson is theirs to report.
    assert await learning_events.mark_abandoned(db, idle_hours=24, owner_id=user.id) == 1
    assert await learning_events.mark_abandoned(db, idle_hours=24, owner_id=user.id) == 0
    assert await count(db, other_user, SESSION_ABANDONED) == 0

    # Came back, then left again: a second, distinct fact.
    session.last_turn_at = utcnow() + timedelta(seconds=1)
    await db.flush()
    later = utcnow() + timedelta(hours=25)
    assert (
        await learning_events.mark_abandoned(
            db, idle_hours=24, owner_id=user.id, now=later
        )
        == 1
    )
    assert await count(db, user, SESSION_ABANDONED) == 2


async def test_recent_and_ended_sessions_are_not_abandoned(
    db: AsyncSession, user: User
) -> None:
    sessions = TeachingSessions(db, user.id)
    recent = (
        await sessions.start_or_resume(
            session_id=None, notebook_id=None, learning_goal="a"
        )
    ).session
    recent.last_turn_at = utcnow() - timedelta(hours=2)
    ended = (
        await sessions.start_or_resume(
            session_id=None, notebook_id=None, learning_goal="b"
        )
    ).session
    ended.last_turn_at = utcnow() - timedelta(hours=48)
    await sessions.end(ended)

    assert await learning_events.mark_abandoned(db, idle_hours=24, owner_id=user.id) == 0
