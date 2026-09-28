"""What Mino remembers about a learner is theirs to see and to forget.

`GET /ai/journeys/{id}/memory` and the four DELETEs behind Settings → "Your
data". Called as functions, like the rest of the DB tests; the owner scoping
is the repository's, so another account's journey is a 404, never a 403.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.api.v1.journeys import (
    ForgetMisconceptionIn,
    forget_journey_memory,
    forget_misconception,
    forget_pattern,
    forget_summary,
    journey_memory,
)
from noema.core.errors import NotFound
from noema.db.models import LearningJourney, MemorySummary, StudentConceptState, User
from noema.professor.memory import merge_profile
from noema.professor.student import StudentModel

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
BELIEF = "tudo que esqueci está no inconsciente"


@pytest.fixture
async def journey(db: AsyncSession, user: User) -> LearningJourney:
    made = LearningJourney(
        owner_id=user.id,
        goal="Entender Freud",
        subject="Psicanálise",
        plan={"modules": []},
        profile={
            "language": "pt",
            "focus": {"chunk_level": 2},
            "patterns": ["analogias funcionam", "precisa da fórmula primeiro"],
            "communication": {"verbosity": "lower", "explanation_depth": "deeper"},
        },
    )
    db.add(made)
    await db.flush()
    for i, level in enumerate(("session", "session", "module")):
        db.add(
            MemorySummary(
                owner_id=user.id,
                journey_id=made.id,
                level=level,
                turn_from=i * 4,
                turn_to=i * 4 + 3,
                summary={
                    "concepts_covered": ["inconsciente"],
                    "misconceptions": [BELIEF],
                    "learner_patterns": ["Analogias funcionam"],
                    "last_taught": f"trecho {i}",
                    "next_step": "recalque",
                },
                created_at=NOW + timedelta(minutes=i),
                superseded_at=NOW if i == 0 else None,
            )
        )
    student = StudentModel(db, user.id, made)
    state = await student.ensure("inconsciente")
    state.misconceptions = [BELIEF]
    state.notes = ["a analogia do iceberg"]
    await db.flush()
    return made


async def _summaries(db: AsyncSession, journey: LearningJourney) -> list[MemorySummary]:
    rows = await db.execute(
        select(MemorySummary)
        .where(MemorySummary.journey_id == journey.id)
        .order_by(MemorySummary.created_at)
    )
    return list(rows.scalars())


async def test_memory_is_shown_in_plain_terms(
    db: AsyncSession, user: User, journey: LearningJourney
) -> None:
    out = await journey_memory(journey.id, user=user, db=db)

    assert out.patterns == ["analogias funcionam", "precisa da fórmula primeiro"]
    assert [(p.label, p.value) for p in out.communication] == [
        ("verbosity", "lower"),
        ("explanation_depth", "deeper"),
    ]
    # Superseded rows are audit, not memory: two of the three summaries show.
    assert [(s.level, s.text, s.next_step) for s in out.summaries] == [
        ("module", "trecho 2", "recalque"),
        ("session", "trecho 1", "recalque"),
    ]
    assert [(m.concept, m.text) for m in out.misconceptions] == [("inconsciente", BELIEF)]


async def test_another_account_sees_nothing_and_forgets_nothing(
    db: AsyncSession, other_user: User, journey: LearningJourney
) -> None:
    with pytest.raises(NotFound):
        await journey_memory(journey.id, user=other_user, db=db)
    with pytest.raises(NotFound):
        await forget_pattern(journey.id, 0, user=other_user, db=db)
    with pytest.raises(NotFound):
        await forget_journey_memory(journey.id, user=other_user, db=db)
    summary = (await _summaries(db, journey))[0]
    with pytest.raises(NotFound):
        await forget_summary(journey.id, summary.id, user=other_user, db=db)
    with pytest.raises(NotFound):
        await forget_misconception(
            journey.id,
            ForgetMisconceptionIn(concept="inconsciente", text=BELIEF),
            user=other_user,
            db=db,
        )
    await db.refresh(journey)
    assert len(journey.profile["patterns"]) == 2
    assert len(await _summaries(db, journey)) == 3


async def test_a_forgotten_pattern_leaves_the_profile_and_the_summaries(
    db: AsyncSession, user: User, journey: LearningJourney
) -> None:
    await forget_pattern(journey.id, 0, user=user, db=db)

    await db.refresh(journey)
    assert journey.profile["patterns"] == ["precisa da fórmula primeiro"]
    assert journey.profile["communication"] == {
        "verbosity": "lower",
        "explanation_depth": "deeper",
    }
    for s in await _summaries(db, journey):
        assert s.summary["learner_patterns"] == []
    # The next compaction merges the profile with its own new summary only,
    # so the forgotten line does not come back from what was stored before.
    merged = merge_profile(journey.profile, {"learner_patterns": ["pergunta por quê"]})
    assert merged["patterns"] == ["precisa da fórmula primeiro", "pergunta por quê"]
    with pytest.raises(NotFound):
        await forget_pattern(journey.id, 5, user=user, db=db)


async def test_a_forgotten_summary_is_gone_and_the_others_stay(
    db: AsyncSession, user: User, journey: LearningJourney
) -> None:
    before = await _summaries(db, journey)
    await forget_summary(journey.id, before[1].id, user=user, db=db)

    after = await _summaries(db, journey)
    assert [s.id for s in after] == [before[0].id, before[2].id]
    with pytest.raises(NotFound):
        await forget_summary(journey.id, before[1].id, user=user, db=db)


async def test_a_summary_of_another_journey_is_not_reachable_through_this_one(
    db: AsyncSession, user: User, journey: LearningJourney
) -> None:
    other = LearningJourney(
        owner_id=user.id, goal="Kant", subject="Filosofia", plan={"modules": []}
    )
    db.add(other)
    await db.flush()
    summary = (await _summaries(db, journey))[0]
    with pytest.raises(NotFound):
        await forget_summary(other.id, summary.id, user=user, db=db)
    assert len(await _summaries(db, journey)) == 3


async def test_a_forgotten_misconception_leaves_the_concept_and_the_summaries(
    db: AsyncSession, user: User, journey: LearningJourney
) -> None:
    await forget_misconception(
        journey.id,
        ForgetMisconceptionIn(concept="inconsciente", text=BELIEF),
        user=user,
        db=db,
    )

    state = await StudentModel(db, user.id, journey).get("inconsciente")
    assert state is not None
    assert state.misconceptions == []
    assert state.notes == ["a analogia do iceberg"]  # a note is not a misconception
    for s in await _summaries(db, journey):
        assert s.summary["misconceptions"] == []
    with pytest.raises(NotFound):
        await forget_misconception(
            journey.id,
            ForgetMisconceptionIn(concept="inconsciente", text="never said"),
            user=user,
            db=db,
        )
    with pytest.raises(NotFound):
        await forget_misconception(
            journey.id,
            ForgetMisconceptionIn(concept="recalque", text=BELIEF),
            user=user,
            db=db,
        )


async def test_forgetting_everything_keeps_the_plan_the_evidence_and_the_language(
    db: AsyncSession, user: User, journey: LearningJourney
) -> None:
    student = StudentModel(db, user.id, journey)
    await student.record("inconsciente", kind="quiz", score=1.0, now=NOW)
    await forget_journey_memory(journey.id, user=user, db=db)

    await db.refresh(journey)
    assert journey.profile == {"language": "pt", "focus": {"chunk_level": 2}}
    assert journey.plan == {"modules": []}
    assert await _summaries(db, journey) == []
    state = await db.scalar(
        select(StudentConceptState).where(StudentConceptState.journey_id == journey.id)
    )
    assert state is not None
    assert state.misconceptions == [] and state.notes == []
    assert state.evidence_count == 1  # the showing itself is not memory
    out = await journey_memory(journey.id, user=user, db=db)
    assert out.patterns == [] and out.communication == []
    assert out.summaries == [] and out.misconceptions == []


async def test_a_journey_that_does_not_exist_is_a_404(
    db: AsyncSession, user: User
) -> None:
    with pytest.raises(NotFound):
        await journey_memory(uuid.uuid4(), user=user, db=db)
