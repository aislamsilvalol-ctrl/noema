"""Reviews, scheduling and the mastery projection, against a real database.

The FSRS and mastery engines are already tested as pure functions. What is tested
here is the wiring: that evidence is written, that projections follow from it, and
that a rebuild from the log would produce the same answer.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.base import utcnow
from noema.db.models import (
    Card,
    CardOrigin,
    CardSchedule,
    CardState,
    Concept,
    ConceptEdge,
    ConceptMastery,
    ConceptStatus,
    EdgeKind,
    Notebook,
    Review,
    Subject,
    User,
    Workspace,
)
from noema.db.repository import OwnedRepository
from noema.engines.fsrs import Rating
from noema.study.mastery import recompute_mastery
from noema.study.review import ReviewOutcome, record_review


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


async def make_concept(
    db: AsyncSession, user: User, notebook: Notebook, name: str
) -> Concept:
    subject = await db.get(Subject, notebook.subject_id)
    assert subject is not None
    concept = Concept(
        owner_id=user.id,
        workspace_id=subject.workspace_id,
        name=name,
        normalized_name=name.lower(),
        status=ConceptStatus.ACTIVE,
        difficulty_prior=0.5,
        aliases=[],
        source_chunk_ids=[],
    )
    db.add(concept)
    await db.flush()
    return concept


async def make_card(
    db: AsyncSession,
    user: User,
    notebook: Notebook,
    concept: Concept | None = None,
    front: str = "What does the chain rule do?",
) -> Card:
    card = Card(
        owner_id=user.id,
        notebook_id=notebook.id,
        concept_id=concept.id if concept else None,
        front_md=front,
        back_md="Differentiates a composition.",
        origin=CardOrigin.USER,
        approved_at=utcnow(),
        source_chunk_ids=[],
    )
    db.add(card)
    await db.flush()
    return card


async def review(
    db: AsyncSession,
    user: User,
    card: Card,
    rating: Rating,
    *,
    confidence: int | None = None,
    now: datetime | None = None,
) -> ReviewOutcome:
    return await record_review(
        db,
        card.id,
        owner_id=user.id,
        rating=rating,
        confidence=confidence,
        now=now,
    )


# ── Scheduling ────────────────────────────────────────────────────────────────


async def test_a_first_review_creates_a_schedule_and_an_evidence_row(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    card = await make_card(db, user, notebook)

    outcome = await review(db, user, card, Rating.GOOD)

    schedule = await db.scalar(
        select(CardSchedule).where(CardSchedule.card_id == card.id)
    )
    assert schedule is not None
    assert schedule.reps == 1
    assert schedule.state is CardState.REVIEW

    evidence = (await db.scalars(select(Review).where(Review.card_id == card.id))).all()
    assert len(evidence) == 1
    assert evidence[0].rating == int(Rating.GOOD)
    assert evidence[0].state_before is None  # nothing preceded it
    assert evidence[0].state_after["stability"] == pytest.approx(outcome.stability)


async def test_the_evidence_log_records_the_state_on_both_sides(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    """A projection can only be rebuilt if each step recorded what it started from."""
    card = await make_card(db, user, notebook)

    await review(db, user, card, Rating.GOOD)
    await review(db, user, card, Rating.GOOD)

    rows = (
        await db.scalars(
            select(Review).where(Review.card_id == card.id).order_by(Review.reviewed_at)
        )
    ).all()
    assert rows[1].state_before is not None
    assert rows[1].state_before["stability"] == pytest.approx(
        rows[0].state_after["stability"]
    )


async def test_repeated_success_pushes_the_due_date_further_out(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    card = await make_card(db, user, notebook)

    first = await review(db, user, card, Rating.GOOD)
    second = await review(
        db, user, card, Rating.GOOD, now=utcnow() + timedelta(days=first.scheduled_days)
    )

    assert second.scheduled_days > first.scheduled_days


async def test_a_failure_brings_the_card_back_within_the_session(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    """Tomorrow is too late for a card you just failed; the point is to fix it now."""
    card = await make_card(db, user, notebook)
    await review(db, user, card, Rating.GOOD)

    outcome = await review(db, user, card, Rating.AGAIN)

    assert outcome.state is CardState.RELEARNING
    assert outcome.scheduled_days < 0.02  # minutes, not days

    schedule = await db.scalar(
        select(CardSchedule).where(CardSchedule.card_id == card.id)
    )
    assert schedule is not None and schedule.lapses == 1


async def test_easy_schedules_further_out_than_hard(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    easy_card = await make_card(db, user, notebook, front="easy")
    hard_card = await make_card(db, user, notebook, front="hard")

    easy = await review(db, user, easy_card, Rating.EASY)
    hard = await review(db, user, hard_card, Rating.HARD)

    assert easy.scheduled_days > hard.scheduled_days


async def test_reviewing_another_users_card_is_refused(
    db: AsyncSession, user: User, other_user: User, notebook: Notebook
) -> None:
    from noema.core.errors import NotFound

    card = await make_card(db, user, notebook)
    with pytest.raises(NotFound):
        await record_review(db, card.id, owner_id=other_user.id, rating=Rating.GOOD)


# ── Mastery ───────────────────────────────────────────────────────────────────


async def test_a_review_produces_a_mastery_projection_with_its_workings(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Chain Rule")
    card = await make_card(db, user, notebook, concept)

    outcome = await review(db, user, card, Rating.GOOD)

    assert outcome.mastery is not None
    row = await db.scalar(
        select(ConceptMastery).where(ConceptMastery.concept_id == concept.id)
    )
    assert row is not None
    assert row.mastery == pytest.approx(outcome.mastery)
    # The decomposition is stored so the UI can explain the number, not assert it.
    assert {"competence", "retrievability", "prior_mean"} <= set(row.components)


async def test_thin_evidence_is_marked_provisional(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Chain Rule")
    card = await make_card(db, user, notebook, concept)

    await review(db, user, card, Rating.GOOD)

    row = await db.scalar(
        select(ConceptMastery).where(ConceptMastery.concept_id == concept.id)
    )
    assert row is not None
    assert row.components["provisional"] is True


async def test_sustained_success_raises_mastery_and_failure_lowers_it(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    good = await make_concept(db, user, notebook, "Known")
    bad = await make_concept(db, user, notebook, "Shaky")
    good_card = await make_card(db, user, notebook, good, front="known")
    bad_card = await make_card(db, user, notebook, bad, front="shaky")

    now = utcnow()
    for index in range(8):
        moment = now + timedelta(days=index)
        await review(db, user, good_card, Rating.GOOD, now=moment)
        await review(db, user, bad_card, Rating.AGAIN, now=moment)

    good_row = await db.scalar(
        select(ConceptMastery).where(ConceptMastery.concept_id == good.id)
    )
    bad_row = await db.scalar(
        select(ConceptMastery).where(ConceptMastery.concept_id == bad.id)
    )
    assert good_row is not None and bad_row is not None
    assert good_row.mastery > bad_row.mastery
    assert bad_row.mastery < 40


async def test_a_confident_wrong_answer_shows_up_as_overconfidence(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    """The signal the misconception engine will consume in Phase 4."""
    concept = await make_concept(db, user, notebook, "Misunderstood")
    card = await make_card(db, user, notebook, concept)

    now = utcnow()
    for index in range(4):
        await review(
            db, user, card, Rating.AGAIN, confidence=5, now=now + timedelta(days=index)
        )

    row = await db.scalar(
        select(ConceptMastery).where(ConceptMastery.concept_id == concept.id)
    )
    assert row is not None
    assert row.calibration > 0.3


async def test_mastery_of_a_prerequisite_moves_what_we_believe_about_its_dependent(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    """Improving the chain rule genuinely changes the belief about backpropagation,
    even though no card of backpropagation was answered."""
    chain_rule = await make_concept(db, user, notebook, "Chain Rule")
    backprop = await make_concept(db, user, notebook, "Backpropagation")
    db.add(
        ConceptEdge(
            owner_id=user.id,
            src_id=chain_rule.id,
            dst_id=backprop.id,
            kind=EdgeKind.PREREQUISITE_OF,
            weight=1.0,
        )
    )
    await db.flush()

    await recompute_mastery(db, backprop.id, owner_id=user.id)
    before = await db.scalar(
        select(ConceptMastery.mastery).where(ConceptMastery.concept_id == backprop.id)
    )

    card = await make_card(db, user, notebook, chain_rule)
    now = utcnow()
    for index in range(6):
        await review(db, user, card, Rating.EASY, now=now + timedelta(days=index * 2))

    after = await db.scalar(
        select(ConceptMastery.mastery).where(ConceptMastery.concept_id == backprop.id)
    )
    assert before is not None and after is not None
    assert after > before


async def test_a_card_without_a_concept_reviews_without_mastery(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    card = await make_card(db, user, notebook, concept=None)

    outcome = await review(db, user, card, Rating.GOOD)

    assert outcome.mastery is None
    assert (await db.scalars(select(ConceptMastery))).all() == []


async def test_mastery_is_scoped_to_its_owner(
    db: AsyncSession, user: User, other_user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Chain Rule")
    card = await make_card(db, user, notebook, concept)
    await review(db, user, card, Rating.GOOD)

    assert await recompute_mastery(db, concept.id, owner_id=other_user.id) is None
