"""Progress earned only from learning, and only once."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.base import utcnow
from noema.db.models import (
    Card,
    CardOrigin,
    ConceptState,
    LearningJourney,
    Notebook,
    Review,
    StudentConceptState,
    StudySession,
    Subject,
    User,
    Workspace,
    XpEvent,
)
from noema.db.repository import OwnedRepository
from noema.services.progression import (
    MARK_XP,
    MASTERED_XP,
    SESSIONS_PER_DAY,
    ProgressionEngine,
)

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 9, 25, 15, 0, tzinfo=UTC)


@pytest.fixture
async def notebook(db: AsyncSession, user: User) -> Notebook:
    workspace = await OwnedRepository(db, Workspace, user.id).create(
        title="CS", slug=f"cs-{uuid.uuid4().hex[:8]}"
    )
    subject = await OwnedRepository(db, Subject, user.id).create(
        workspace_id=workspace.id, title="ML", slug=f"ml-{uuid.uuid4().hex[:8]}"
    )
    return await OwnedRepository(db, Notebook, user.id).create(
        subject_id=subject.id,
        title="Opt",
        slug=f"opt-{uuid.uuid4().hex[:8]}",
        retrieval_settings={},
    )


async def card(db: AsyncSession, user: User, notebook: Notebook) -> Card:
    made = Card(
        owner_id=user.id,
        notebook_id=notebook.id,
        front_md="Q",
        back_md="A",
        origin=CardOrigin.USER,
        approved_at=utcnow(),
        source_chunk_ids=[],
    )
    db.add(made)
    await db.flush()
    return made


def review(user: User, made: Card, at: datetime, rating: int = 3) -> Review:
    return Review(
        owner_id=user.id, card_id=made.id, rating=rating, state_after={}, reviewed_at=at
    )


async def total(db: AsyncSession, user: User, kind: str | None = None) -> int:
    query = select(func.coalesce(func.sum(XpEvent.xp), 0)).where(
        XpEvent.owner_id == user.id
    )
    if kind:
        query = query.where(XpEvent.kind == kind)
    return int(await db.scalar(query) or 0)


async def test_counting_twice_earns_nothing_more(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    made = await card(db, user, notebook)
    db.add(review(user, made, NOW))
    await db.flush()
    engine = ProgressionEngine(db, user.id)

    await engine.sync(now=NOW)
    first = await total(db, user)
    await engine.sync(now=NOW)

    assert first > 0
    assert await total(db, user) == first


async def test_cramming_one_card_pays_once_a_day(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    made = await card(db, user, notebook)
    for minutes in range(5):
        db.add(review(user, made, NOW + timedelta(minutes=minutes)))
    db.add(review(user, made, NOW + timedelta(days=1)))
    await db.flush()

    await ProgressionEngine(db, user.id).sync(now=NOW + timedelta(days=1))

    assert await total(db, user, "review") == 20  # two days, ten each


async def test_planned_sessions_count_three_a_day(db: AsyncSession, user: User) -> None:
    for minutes in range(SESSIONS_PER_DAY + 2):
        db.add(
            StudySession(
                owner_id=user.id,
                planned_minutes=10,
                started_at=NOW,
                completed_at=NOW + timedelta(minutes=minutes),
            )
        )
    await db.flush()

    await ProgressionEngine(db, user.id).sync(now=NOW)

    assert await total(db, user, "session") == 30 * SESSIONS_PER_DAY


async def test_a_mastered_concept_pays_once_and_leaves_a_mark(
    db: AsyncSession, user: User
) -> None:
    journey = LearningJourney(owner_id=user.id, goal="cálculo")
    db.add(journey)
    await db.flush()
    db.add(
        StudentConceptState(
            owner_id=user.id,
            journey_id=journey.id,
            name="Derivadas",
            normalized_name="derivadas",
            state=ConceptState.MASTERED.value,
        )
    )
    await db.flush()
    engine = ProgressionEngine(db, user.id)

    await engine.sync(now=NOW)
    await engine.sync(now=NOW)

    assert await total(db, user, "concept_mastered") == MASTERED_XP
    summary = await engine.summary(now=NOW)
    first = next(m for m in summary.marks if m.id == "first_mastered")
    assert first.earned
    assert await total(db, user, "mark") == MARK_XP


async def test_a_finished_daily_mission_is_granted_once(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    for _ in range(3):
        made = await card(db, user, notebook)
        db.add(review(user, made, NOW))
    await db.flush()
    engine = ProgressionEngine(db, user.id)

    await engine.sync(now=NOW)
    await engine.sync(now=NOW)

    recall = next(m for m in await engine.missions(now=NOW) if m.id == "recall")
    assert recall.done
    granted = await db.scalar(
        select(func.count())
        .select_from(XpEvent)
        .where(XpEvent.owner_id == user.id, XpEvent.kind == "mission")
    )
    assert granted == 1


async def test_nothing_learned_nothing_earned(db: AsyncSession, user: User) -> None:
    engine = ProgressionEngine(db, user.id)
    await engine.sync(now=NOW)

    summary = await engine.summary(now=NOW)

    assert summary.xp_total == 0 and summary.level == 1
    assert not any(m.done for m in summary.missions)
    assert not any(m.earned for m in summary.marks)
