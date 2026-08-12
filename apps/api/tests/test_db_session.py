"""The learning session, against a real database.

The engine is tested as pure functions elsewhere. What is tested here is that the
right candidates reach it, with the right numbers attached.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.base import utcnow
from noema.db.models import (
    Card,
    CardOrigin,
    Concept,
    ConceptEdge,
    ConceptStatus,
    Difficulty,
    EdgeKind,
    Notebook,
    Question,
    QuestionType,
    Subject,
    User,
    Workspace,
)
from noema.db.repository import OwnedRepository
from noema.engines.fsrs import Rating
from noema.engines.scheduler import ItemKind
from noema.study.mastery import recompute_mastery
from noema.study.questions import answer_question
from noema.study.review import record_review
from noema.study.session import gather_candidates, plan_session


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
    *,
    concept: Concept | None = None,
    approved: bool = True,
    front: str = "front",
) -> Card:
    card = Card(
        owner_id=user.id,
        notebook_id=notebook.id,
        concept_id=concept.id if concept else None,
        front_md=front,
        back_md="back",
        origin=CardOrigin.USER,
        approved_at=utcnow() if approved else None,
        source_chunk_ids=[],
    )
    db.add(card)
    await db.flush()
    return card


async def make_question(
    db: AsyncSession, user: User, notebook: Notebook, concept: Concept
) -> Question:
    question = Question(
        owner_id=user.id,
        notebook_id=notebook.id,
        concept_id=concept.id,
        type=QuestionType.MCQ,
        difficulty=Difficulty.MEDIUM,
        prompt="Which one?",
        payload={"correct_index": 1, "options": ["a", "b"]},
        source_chunk_ids=[],
    )
    db.add(question)
    await db.flush()
    return question


async def kinds(
    db: AsyncSession, user: User, now: datetime | None = None
) -> set[ItemKind]:
    candidates = await gather_candidates(db, owner_id=user.id, now=now or utcnow())
    return {c.kind for c in candidates}


# ── Candidates ────────────────────────────────────────────────────────────────


async def test_an_unreviewed_card_is_offered_as_new_material(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    await make_card(db, user, notebook)
    assert ItemKind.CARD_LEARN in await kinds(db, user)


async def test_an_unapproved_card_is_never_offered(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    """The approval gate has to hold here too, or generation quietly bypasses it."""
    await make_card(db, user, notebook, approved=False)
    assert await gather_candidates(db, owner_id=user.id, now=utcnow()) == []


async def test_a_due_card_is_offered_for_review(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    card = await make_card(db, user, notebook)
    await record_review(db, card.id, owner_id=user.id, rating=Rating.GOOD)

    later = utcnow() + timedelta(days=30)
    assert ItemKind.CARD_REVIEW in await kinds(db, user, later)


async def test_a_card_not_yet_due_is_not_offered(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    card = await make_card(db, user, notebook)
    await record_review(db, card.id, owner_id=user.id, rating=Rating.EASY)

    assert ItemKind.CARD_REVIEW not in await kinds(db, user)


async def test_a_misconception_becomes_a_drill(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Backpropagation")
    question = await make_question(db, user, notebook, concept)
    await answer_question(db, question.id, {"choice": 0}, owner_id=user.id, confidence=5)

    candidates = await gather_candidates(db, owner_id=user.id, now=utcnow())
    drills = [c for c in candidates if c.kind is ItemKind.MISCONCEPTION_DRILL]

    assert drills
    assert drills[0].is_misconception
    assert drills[0].concept_name == "Backpropagation"


async def test_another_users_material_is_never_offered(
    db: AsyncSession, user: User, other_user: User, notebook: Notebook
) -> None:
    await make_card(db, user, notebook)
    assert await gather_candidates(db, owner_id=other_user.id, now=utcnow()) == []


async def test_a_card_on_a_prerequisite_of_a_failing_concept_is_flagged(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    """The rerouting rule: when a concept keeps failing, its prerequisites are what
    the learner should see first."""
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

    # Make backpropagation measurably weak.
    failing_card = await make_card(db, user, notebook, concept=backprop, front="bp")
    now = utcnow()
    for index in range(6):
        await record_review(
            db,
            failing_card.id,
            owner_id=user.id,
            rating=Rating.AGAIN,
            now=now + timedelta(minutes=index * 20),
        )

    prerequisite_card = await make_card(
        db, user, notebook, concept=chain_rule, front="cr"
    )
    await record_review(
        db, prerequisite_card.id, owner_id=user.id, rating=Rating.GOOD, now=now
    )

    candidates = await gather_candidates(
        db, owner_id=user.id, now=now + timedelta(days=30)
    )
    flagged = [c for c in candidates if c.blocks_failing_concept]

    assert flagged
    assert all(c.concept_id == chain_rule.id for c in flagged)


# ── Plan ──────────────────────────────────────────────────────────────────────


async def test_an_empty_account_gets_an_honest_empty_plan(
    db: AsyncSession, user: User
) -> None:
    plan = await plan_session(db, owner_id=user.id, minutes=30)
    assert plan.blocks == []
    assert "Nothing is due" in plan.rationale


async def test_a_plan_fits_its_budget_and_explains_itself(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Gradient Descent")
    for index in range(30):
        await make_card(db, user, notebook, concept=concept, front=f"card {index}")

    plan = await plan_session(db, owner_id=user.id, minutes=10)

    assert plan.items
    assert plan.estimated_seconds <= 10 * 60
    assert plan.rationale
    for block in plan.blocks:
        assert block.why


async def test_a_misconception_leads_the_session(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Backpropagation")
    question = await make_question(db, user, notebook, concept)
    await answer_question(db, question.id, {"choice": 0}, owner_id=user.id, confidence=5)

    for index in range(10):
        await make_card(db, user, notebook, front=f"filler {index}")

    plan = await plan_session(db, owner_id=user.id, minutes=30)

    assert "Backpropagation" in plan.rationale
    assert any(item.is_misconception for item in plan.items)


async def test_the_planner_measures_the_learners_pace_rather_than_assuming_it(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    """An estimate that never improves is decoration on a time budget."""
    card = await make_card(db, user, notebook)

    now = utcnow()
    for index in range(12):
        await record_review(
            db,
            card.id,
            owner_id=user.id,
            rating=Rating.GOOD,
            elapsed_ms=25_000,  # a deliberate, slow reader
            now=now + timedelta(days=index * 3),
        )

    await make_card(db, user, notebook, front="second")
    candidates = await gather_candidates(
        db, owner_id=user.id, now=now + timedelta(days=400)
    )

    reviews = [c for c in candidates if c.kind is ItemKind.CARD_REVIEW]
    assert reviews
    assert reviews[0].cost_seconds == pytest.approx(25.0, abs=1.0)


async def test_importance_rises_with_what_a_concept_blocks(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    foundational = await make_concept(db, user, notebook, "Foundational")
    isolated = await make_concept(db, user, notebook, "Isolated")

    for index in range(3):
        dependent = await make_concept(db, user, notebook, f"Dependent {index}")
        db.add(
            ConceptEdge(
                owner_id=user.id,
                src_id=foundational.id,
                dst_id=dependent.id,
                kind=EdgeKind.PREREQUISITE_OF,
                weight=1.0,
            )
        )
    await db.flush()

    for concept in (foundational, isolated):
        card = await make_card(db, user, notebook, concept=concept, front=str(concept.id))
        await record_review(db, card.id, owner_id=user.id, rating=Rating.HARD)
        await recompute_mastery(db, concept.id, owner_id=user.id)

    candidates = await gather_candidates(
        db, owner_id=user.id, now=utcnow() + timedelta(days=10)
    )
    by_concept = {c.concept_id: c.importance for c in candidates}

    assert by_concept[foundational.id] > by_concept[isolated.id]
