"""The concept clock reads the FSRS schedule a real review just wrote.

Pure dates are in ``test_concept_review.py``. This is the wiring: two cards
graded into different memory states land on different concept dates, a
concept with no schedule stays on the seven-day fallback, and a draft does
not move the clock.
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
    CardSchedule,
    CardState,
    Concept,
    ConceptStatus,
    LearningJourney,
    Notebook,
    StudentConceptState,
    Subject,
    User,
    Workspace,
)
from noema.db.repository import OwnedRepository
from noema.engines.fsrs import Rating
from noema.professor.student import (
    StudentModel,
    concept_review_due,
    next_concept_review_at,
)
from noema.study.review import record_review

pytestmark = pytest.mark.asyncio


async def _notebook(db: AsyncSession, user: User) -> Notebook:
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


async def _concept(
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


async def _card(
    db: AsyncSession,
    user: User,
    notebook: Notebook,
    concept: Concept,
    *,
    approved: bool,
) -> Card:
    card = Card(
        owner_id=user.id,
        notebook_id=notebook.id,
        concept_id=concept.id,
        concept_name=concept.name,
        front_md=f"O que é {concept.name}?",
        back_md="Uma resposta.",
        origin=CardOrigin.USER,
        approved_at=utcnow() if approved else None,
        source_chunk_ids=[],
    )
    db.add(card)
    await db.flush()
    return card


def _state(
    user: User,
    journey: LearningJourney,
    concept: Concept,
    *,
    when: datetime,
) -> StudentConceptState:
    return StudentConceptState(
        owner_id=user.id,
        journey_id=journey.id,
        concept_id=concept.id,
        name=concept.name,
        normalized_name=concept.normalized_name,
        state="mastered",
        score=0.9,
        evidence_count=4,
        strong_evidence_count=2,
        misconceptions=[],
        notes=[],
        last_evidence_at=when,
    )


async def test_fsrs_states_schedule_different_concept_reviews(
    db: AsyncSession, user: User
) -> None:
    notebook = await _notebook(db, user)
    shown = utcnow()
    hard_concept = await _concept(db, user, notebook, "Cadeia")
    easy_concept = await _concept(db, user, notebook, "Gradiente")
    quiet_concept = await _concept(db, user, notebook, "Vies")
    draft_concept = await _concept(db, user, notebook, "Rascunho")

    journey = LearningJourney(owner_id=user.id, goal="cálculo", notebook_id=notebook.id)
    db.add(journey)
    await db.flush()
    for concept in (hard_concept, easy_concept, quiet_concept, draft_concept):
        db.add(_state(user, journey, concept, when=shown))
    await db.flush()

    hard_card = await _card(db, user, notebook, hard_concept, approved=True)
    easy_card = await _card(db, user, notebook, easy_concept, approved=True)
    await record_review(db, hard_card.id, owner_id=user.id, rating=Rating.HARD, now=shown)
    await record_review(db, easy_card.id, owner_id=user.id, rating=Rating.EASY, now=shown)

    draft = await _card(db, user, notebook, draft_concept, approved=False)
    db.add(
        CardSchedule(
            owner_id=user.id,
            card_id=draft.id,
            due_at=shown - timedelta(days=1),
            stability=1.0,
            difficulty=5.0,
            reps=1,
            lapses=0,
            state=CardState.REVIEW,
        )
    )
    await db.flush()

    model = StudentModel(db, user.id, journey)
    by_id, _by_name = await model.card_due_index()
    hard_due = next_concept_review_at(shown, by_id[hard_concept.id])
    easy_due = next_concept_review_at(shown, by_id[easy_concept.id])
    assert hard_due is not None and easy_due is not None
    assert hard_due != easy_due
    assert hard_due < easy_due

    later = shown + timedelta(days=3)
    assert concept_review_due(
        stage="mastered",
        last_evidence_at=shown,
        card_due_ats=by_id[hard_concept.id],
        now=later,
    )
    assert not concept_review_due(
        stage="mastered",
        last_evidence_at=shown,
        card_due_ats=by_id[easy_concept.id],
        now=later,
    )

    # No schedule: still the seven-day fallback, not "due because a card exists".
    assert quiet_concept.id not in by_id
    assert next_concept_review_at(shown, ()) == shown + timedelta(days=7)
    assert not concept_review_due(stage="mastered", last_evidence_at=shown, now=later)
    assert concept_review_due(
        stage="mastered",
        last_evidence_at=shown,
        now=shown + timedelta(days=7, seconds=1),
    )

    # A draft's due_at is not the learner's clock, even when it is already past.
    assert draft_concept.id not in by_id
    assert not concept_review_due(stage="mastered", last_evidence_at=shown, now=later)
