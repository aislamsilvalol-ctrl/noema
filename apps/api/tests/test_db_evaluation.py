"""Evaluating the scheduler against a real review history.

This is the machinery that turns every constant in the scheduler from an assertion
into a hypothesis. If it cannot be trusted, none of the tuning that follows can be.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.base import utcnow
from noema.db.models import (
    Card,
    CardOrigin,
    Notebook,
    StudySession,
    Subject,
    User,
    Workspace,
)
from noema.db.repository import OwnedRepository
from noema.engines import fsrs
from noema.engines.fsrs import Rating
from noema.study.evaluation import (
    evaluate_memory_model,
    evaluate_planner,
    has_enough_history,
    try_weights,
)
from noema.study.review import record_review


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
        title="Optimization",
        slug=f"opt-{uuid.uuid4().hex[:8]}",
        retrieval_settings={},
    )


async def make_card(db: AsyncSession, user: User, notebook: Notebook, front: str) -> Card:
    card = Card(
        owner_id=user.id,
        notebook_id=notebook.id,
        front_md=front,
        back_md="back",
        origin=CardOrigin.USER,
        approved_at=utcnow(),
        source_chunk_ids=[],
    )
    db.add(card)
    await db.flush()
    return card


async def study(
    db: AsyncSession,
    user: User,
    card: Card,
    *,
    times: int,
    rating: Rating,
    gap_days: float,
) -> None:
    start = utcnow() - timedelta(days=gap_days * times + 1)
    for index in range(times):
        await record_review(
            db,
            card.id,
            owner_id=user.id,
            rating=rating,
            now=start + timedelta(days=gap_days * index),
        )


# ── Memory model ──────────────────────────────────────────────────────────────


async def test_a_history_without_reviews_reports_nothing_rather_than_guessing(
    db: AsyncSession, user: User
) -> None:
    result = await evaluate_memory_model(db, owner_id=user.id)

    assert result.attempts == 0
    assert not has_enough_history(result)


async def test_the_replay_scores_predictions_against_what_happened(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    card = await make_card(db, user, notebook, "front")
    await study(db, user, card, times=8, rating=Rating.GOOD, gap_days=3)

    result = await evaluate_memory_model(db, owner_id=user.id)

    assert result.attempts == 7  # eight reviews, seven predictions
    assert result.actual_recall == 1.0
    assert 0 < result.mean_predicted <= 1
    assert result.summary()


async def test_a_learner_who_keeps_failing_shows_the_model_as_optimistic(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    card = await make_card(db, user, notebook, "hard")
    await study(db, user, card, times=10, rating=Rating.AGAIN, gap_days=1)

    result = await evaluate_memory_model(db, owner_id=user.id)

    assert result.actual_recall == 0.0
    assert result.optimistic
    assert "optimistic" in result.summary().lower()


async def test_thin_history_is_marked_unreliable_rather_than_reported_as_fact(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    """Five reviews cannot tell you whether a memory model is calibrated, and saying
    so is the difference between a metric and a number."""
    card = await make_card(db, user, notebook, "front")
    await study(db, user, card, times=5, rating=Rating.GOOD, gap_days=2)

    assert not has_enough_history(await evaluate_memory_model(db, owner_id=user.id))


async def test_a_candidate_weight_set_is_scored_on_the_same_history(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    """The whole point: a scheduler change becomes an experiment, not an opinion."""
    for index in range(4):
        card = await make_card(db, user, notebook, f"card {index}")
        await study(db, user, card, times=6, rating=Rating.GOOD, gap_days=4)

    optimistic = list(fsrs.DEFAULT_WEIGHTS)
    optimistic[8] += 2.0

    baseline, candidate, better = await try_weights(
        db, owner_id=user.id, candidate=tuple(optimistic)
    )

    assert baseline.attempts == candidate.attempts > 0
    assert baseline.mean_predicted != candidate.mean_predicted
    assert isinstance(better, bool)


async def test_another_users_history_is_never_scored(
    db: AsyncSession, user: User, other_user: User, notebook: Notebook
) -> None:
    card = await make_card(db, user, notebook, "front")
    await study(db, user, card, times=6, rating=Rating.GOOD, gap_days=2)

    assert (await evaluate_memory_model(db, owner_id=other_user.id)).attempts == 0


async def test_each_card_is_replayed_from_its_own_first_review(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    """Two cards reviewed alternately must not contaminate each other's intervals."""
    first = await make_card(db, user, notebook, "first")
    second = await make_card(db, user, notebook, "second")

    start = utcnow() - timedelta(days=40)
    for index in range(6):
        moment = start + timedelta(days=index * 5)
        await record_review(
            db, first.id, owner_id=user.id, rating=Rating.GOOD, now=moment
        )
        await record_review(
            db, second.id, owner_id=user.id, rating=Rating.GOOD, now=moment
        )

    result = await evaluate_memory_model(db, owner_id=user.id)

    # Twelve reviews, two of which are first exposures with nothing to predict.
    assert result.attempts == 10


# ── Planner ───────────────────────────────────────────────────────────────────


async def test_planner_calibration_is_empty_before_any_session_completes(
    db: AsyncSession, user: User
) -> None:
    calibration = await evaluate_planner(db, owner_id=user.id)

    assert calibration.sessions == 0
    assert "No completed sessions" in calibration.summary()


async def test_a_completed_session_is_compared_against_its_estimate(
    db: AsyncSession, user: User
) -> None:
    record = StudySession(
        owner_id=user.id,
        planned_minutes=30,
        estimated_seconds=1800,
        actual_seconds=2400,  # ran ten minutes over
        rationale="test",
        plan={},
        items_planned=20,
        items_completed=15,
        completed_at=utcnow(),
    )
    db.add(record)
    await db.flush()

    calibration = await evaluate_planner(db, owner_id=user.id)

    assert calibration.sessions == 1
    assert calibration.mean_estimated_minutes == 30.0
    assert calibration.mean_actual_minutes == 40.0
    assert not calibration.overestimates
    assert calibration.completion_rate == 0.75
    assert "under" in calibration.summary()


async def test_an_unfinished_session_is_not_counted(db: AsyncSession, user: User) -> None:
    """A session someone abandoned says nothing about the estimate's accuracy."""
    db.add(
        StudySession(
            owner_id=user.id,
            planned_minutes=30,
            estimated_seconds=1800,
            rationale="test",
            plan={},
            items_planned=20,
            items_completed=0,
        )
    )
    await db.flush()

    assert (await evaluate_planner(db, owner_id=user.id)).sessions == 0


async def test_the_stored_plan_survives_for_replay(db: AsyncSession, user: User) -> None:
    """A plan that is not stored cannot be compared against a later scheduler."""
    stored = {
        "rationale": "Backpropagation is your weakest concept.",
        "blocks": [{"kind": "warmup", "why": "…", "seconds": 90, "items": []}],
    }
    db.add(
        StudySession(
            owner_id=user.id,
            planned_minutes=20,
            estimated_seconds=1200,
            rationale=stored["rationale"],
            plan=stored,
            items_planned=12,
            items_completed=0,
        )
    )
    await db.flush()

    row = (await db.scalars(select(StudySession))).one()
    assert row.plan["blocks"][0]["kind"] == "warmup"
    assert row.rationale.startswith("Backpropagation")
