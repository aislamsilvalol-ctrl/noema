"""Lesson lifecycle facts: started, completed, abandoned.

Each is written from a point that already knows it, never from the engine's
teaching logic:

* **lesson_started** — the first learner turn of a teaching session
  (`TeachingSessions.record_learner`). Source: the session id.
* **lesson_completed** — a lesson whose status in the journey's plan is
  ``done``. Derived from the plan after each Professor turn rather than hooked
  into the advance itself, so it is idempotent by construction and catches up
  on anything a failed turn missed. Source: journey, module and lesson index.
* **session_abandoned** — an open session with no turn for
  ``NOEMA_SESSION_ABANDONED_AFTER_HOURS``. Computed lazily (for one learner,
  when they start a new lesson) and by the `sweep_abandoned_sessions` actor
  for everyone. Source: the session and the last turn's time, so a session
  resumed and left again is a second, distinct fact.

Every write is ``INSERT … ON CONFLICT DO NOTHING`` on (owner, kind, source):
a double submit, a retried request or a re-run sweep records one row.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.logging import get_logger
from noema.db.base import utcnow
from noema.db.models import LearningJourney, LearningLifecycleEvent, TeachingSession

log = get_logger(__name__)

LESSON_STARTED = "lesson_started"
LESSON_COMPLETED = "lesson_completed"
SESSION_ABANDONED = "session_abandoned"

#: How many idle sessions one sweep marks, so a first run over a large backlog
#: is a series of short transactions rather than one long one.
SWEEP_BATCH = 500


async def record(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
    kind: str,
    source_id: str,
    journey_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> bool:
    """Write one fact unless it is already recorded. True if this call wrote it."""
    result = await db.execute(
        insert(LearningLifecycleEvent)
        .values(
            id=uuid.uuid4(),
            owner_id=owner_id,
            kind=kind,
            source_id=source_id[:200],
            journey_id=journey_id,
            session_id=session_id,
            payload=payload or {},
        )
        .on_conflict_do_nothing(constraint="uq_learning_events_source")
        .returning(LearningLifecycleEvent.id)
    )
    written = result.scalar_one_or_none() is not None
    if written:
        log.info("learning_event.recorded", kind=kind)
    return written


async def lesson_started(db: AsyncSession, session: TeachingSession) -> bool:
    return await record(
        db,
        owner_id=session.owner_id,
        kind=LESSON_STARTED,
        source_id=str(session.id),
        journey_id=session.journey_id,
        session_id=session.id,
        payload={
            "notebook_id": str(session.notebook_id) if session.notebook_id else None
        },
    )


async def sync_lesson_completions(
    db: AsyncSession, journey: LearningJourney, *, session_id: uuid.UUID | None = None
) -> int:
    """Record every lesson the plan marks ``done`` that is not yet recorded.

    Skipped lessons are not completions. Returns how many were new.
    """
    written = 0
    modules = (journey.plan or {}).get("modules") or []
    for m, module in enumerate(modules):
        for li, lesson in enumerate(module.get("lessons") or []):
            if lesson.get("status") != "done":
                continue
            if await record(
                db,
                owner_id=journey.owner_id,
                kind=LESSON_COMPLETED,
                source_id=f"{journey.id}:{m}:{li}",
                journey_id=journey.id,
                session_id=session_id,
                payload={
                    "module": m,
                    "lesson": li,
                    "title": str(lesson.get("title") or "")[:160],
                },
            ):
                written += 1
    return written


async def after_professor_turn(
    db: AsyncSession, owner_id: uuid.UUID, session_id: uuid.UUID
) -> int:
    """Called once a Professor turn has finished streaming: catch the plan's
    completions up. Reads the journey fresh — the engine wrote it on its own
    transaction, and this session may hold a stale copy."""
    journey = await db.scalar(
        select(LearningJourney)
        .join(TeachingSession, TeachingSession.journey_id == LearningJourney.id)
        .where(
            TeachingSession.id == session_id,
            TeachingSession.owner_id == owner_id,
            LearningJourney.owner_id == owner_id,
        )
        .execution_options(populate_existing=True)
    )
    if journey is None:
        return 0
    return await sync_lesson_completions(db, journey, session_id=session_id)


async def mark_abandoned(
    db: AsyncSession,
    *,
    idle_hours: int,
    owner_id: uuid.UUID | None = None,
    now: datetime | None = None,
    limit: int = SWEEP_BATCH,
) -> int:
    """Record ``session_abandoned`` for open sessions idle past the threshold.

    For one owner (lazily) or everyone (the sweep). The session itself is not
    ended: a learner may still come back to it, and resuming is not an error.
    """
    if idle_hours <= 0:
        return 0
    cutoff = (now or utcnow()) - timedelta(hours=idle_hours)
    already = (
        select(LearningLifecycleEvent.id)
        .where(
            LearningLifecycleEvent.owner_id == TeachingSession.owner_id,
            LearningLifecycleEvent.session_id == TeachingSession.id,
            LearningLifecycleEvent.kind == SESSION_ABANDONED,
            LearningLifecycleEvent.created_at >= TeachingSession.last_turn_at,
        )
        .exists()
    )
    query = (
        select(TeachingSession)
        .where(
            TeachingSession.ended_at.is_(None),
            TeachingSession.last_turn_at.is_not(None),
            TeachingSession.last_turn_at < cutoff,
            ~already,
        )
        .order_by(TeachingSession.last_turn_at)
        .limit(limit)
    )
    if owner_id is not None:
        query = query.where(TeachingSession.owner_id == owner_id)

    written = 0
    for session in await db.scalars(query):
        assert session.last_turn_at is not None
        if await record(
            db,
            owner_id=session.owner_id,
            kind=SESSION_ABANDONED,
            source_id=f"{session.id}:{session.last_turn_at.isoformat()}",
            journey_id=session.journey_id,
            session_id=session.id,
            payload={
                "turns": session.turn_count,
                "last_turn_at": session.last_turn_at.isoformat(),
            },
        ):
            written += 1
    return written
