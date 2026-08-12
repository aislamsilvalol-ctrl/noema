"""Answering questions, and what follows from it.

The point of questions is that they carry a real difficulty and a real grader, both
of which the mastery engine has always weighted and neither of which a card review
can supply.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.config import Settings
from noema.db.base import utcnow
from noema.db.models import (
    Answer,
    Concept,
    ConceptMastery,
    ConceptStatus,
    Difficulty,
    Grader,
    Mistake,
    Notebook,
    Question,
    QuestionType,
    Subject,
    User,
    Workspace,
)
from noema.db.repository import OwnedRepository
from noema.providers.gateway import AIGateway
from noema.providers.mock import MockProvider
from noema.study.questions import answer_question


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


@pytest.fixture
def gateway(settings: Settings) -> AIGateway:
    return AIGateway(MockProvider(dimensions=settings.noema_embedding_dim))


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


async def make_question(
    db: AsyncSession,
    user: User,
    notebook: Notebook,
    *,
    concept: Concept | None = None,
    kind: QuestionType = QuestionType.MCQ,
    difficulty: Difficulty = Difficulty.MEDIUM,
    payload: dict[str, object] | None = None,
    rubric: dict[str, object] | None = None,
) -> Question:
    question = Question(
        owner_id=user.id,
        notebook_id=notebook.id,
        concept_id=concept.id if concept else None,
        type=kind,
        difficulty=difficulty,
        prompt="What does gradient descent minimise?",
        payload=payload
        if payload is not None
        else {"correct_index": 1, "options": ["a", "b"]},
        rubric=rubric,
        source_chunk_ids=[],
    )
    db.add(question)
    await db.flush()
    return question


async def test_a_right_answer_is_recorded_as_evidence(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Gradient Descent")
    question = await make_question(db, user, notebook, concept=concept)

    answer = await answer_question(db, question.id, {"choice": 1}, owner_id=user.id)

    assert answer.is_correct
    assert answer.score == 1.0
    assert answer.grader is Grader.DETERMINISTIC
    assert answer.concept_id == concept.id


async def test_answering_updates_mastery(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Gradient Descent")
    question = await make_question(db, user, notebook, concept=concept)

    await answer_question(db, question.id, {"choice": 1}, owner_id=user.id)

    row = await db.scalar(
        select(ConceptMastery).where(ConceptMastery.concept_id == concept.id)
    )
    assert row is not None
    assert row.evidence_count > 0


async def test_an_expert_item_moves_mastery_more_than_an_easy_one(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    """This is the whole reason questions exist alongside cards: a card review is
    mid-difficulty by construction and cannot make this distinction."""
    easy_concept = await make_concept(db, user, notebook, "Easy Topic")
    hard_concept = await make_concept(db, user, notebook, "Hard Topic")

    easy_q = await make_question(
        db, user, notebook, concept=easy_concept, difficulty=Difficulty.EASY
    )
    hard_q = await make_question(
        db, user, notebook, concept=hard_concept, difficulty=Difficulty.EXPERT
    )

    now = utcnow()
    for index in range(5):
        moment = now + timedelta(days=index)
        await answer_question(db, easy_q.id, {"choice": 1}, owner_id=user.id, now=moment)
        await answer_question(db, hard_q.id, {"choice": 1}, owner_id=user.id, now=moment)

    easy_row = await db.scalar(
        select(ConceptMastery).where(ConceptMastery.concept_id == easy_concept.id)
    )
    hard_row = await db.scalar(
        select(ConceptMastery).where(ConceptMastery.concept_id == hard_concept.id)
    )
    assert easy_row is not None and hard_row is not None
    assert hard_row.mastery > easy_row.mastery


async def test_partial_credit_reaches_the_evidence_log(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Ordering")
    question = await make_question(
        db,
        user,
        notebook,
        concept=concept,
        kind=QuestionType.ORDERING,
        payload={"order": ["a", "b", "c", "d"]},
    )

    answer = await answer_question(
        db, question.id, {"order": ["a", "b", "d", "c"]}, owner_id=user.id
    )

    assert 0 < answer.score < 1
    assert not answer.is_correct


async def test_a_wrong_answer_lands_in_the_mistake_bank(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Gradient Descent")
    question = await make_question(db, user, notebook, concept=concept)

    await answer_question(db, question.id, {"choice": 0}, owner_id=user.id)

    mistake = (await db.scalars(select(Mistake))).one()
    assert mistake.question_id == question.id
    assert not mistake.is_misconception  # no confidence was stated


async def test_a_confident_wrong_answer_is_flagged_as_a_misconception(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    """The failure spaced repetition never catches: a coherent wrong model, and no
    reason for the learner to flag it for review."""
    concept = await make_concept(db, user, notebook, "Gradient Descent")
    question = await make_question(db, user, notebook, concept=concept)

    await answer_question(db, question.id, {"choice": 0}, owner_id=user.id, confidence=5)

    mistake = (await db.scalars(select(Mistake))).one()
    assert mistake.is_misconception
    assert mistake.confidence == 5


async def test_an_unconfident_wrong_answer_is_a_mistake_but_not_a_misconception(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    concept = await make_concept(db, user, notebook, "Gradient Descent")
    question = await make_question(db, user, notebook, concept=concept)

    await answer_question(db, question.id, {"choice": 0}, owner_id=user.id, confidence=1)

    mistake = (await db.scalars(select(Mistake))).one()
    assert not mistake.is_misconception


async def test_a_right_answer_creates_no_mistake(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    question = await make_question(db, user, notebook)
    await answer_question(db, question.id, {"choice": 1}, owner_id=user.id)
    assert (await db.scalars(select(Mistake))).all() == []


async def test_an_open_answer_is_graded_by_the_model_and_discounted(
    db: AsyncSession, user: User, notebook: Notebook, gateway: AIGateway
) -> None:
    """AI grading is useful but not ground truth, so its evidence weighs less — the
    engine has always supported that and nothing exercised it until now."""
    concept = await make_concept(db, user, notebook, "Open Topic")
    question = await make_question(
        db,
        user,
        notebook,
        concept=concept,
        kind=QuestionType.OPEN,
        payload={},
        rubric={"points": ["mentions the loss function"]},
    )

    answer = await answer_question(
        db,
        question.id,
        {"text": "It minimises a loss function by stepping downhill."},
        owner_id=user.id,
        gateway=gateway,
    )

    assert answer.grader is Grader.AI
    assert answer.feedback is not None


async def test_an_open_answer_without_a_grader_is_not_silently_scored(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    """Without a model there is no honest grade, so the learner is told to grade
    themselves rather than handed a number nobody computed."""
    question = await make_question(
        db,
        user,
        notebook,
        kind=QuestionType.OPEN,
        payload={},
        rubric={"points": ["something"]},
    )

    answer = await answer_question(
        db, question.id, {"text": "An answer."}, owner_id=user.id, gateway=None
    )

    assert answer.grader is Grader.SELF
    assert answer.feedback is not None
    assert "grade yourself" in answer.feedback["feedback"]


async def test_an_empty_open_answer_scores_zero_without_calling_a_model(
    db: AsyncSession, user: User, notebook: Notebook, gateway: AIGateway
) -> None:
    question = await make_question(
        db, user, notebook, kind=QuestionType.OPEN, payload={}, rubric={"points": ["x"]}
    )

    answer = await answer_question(
        db, question.id, {"text": "   "}, owner_id=user.id, gateway=gateway
    )

    assert answer.score == 0.0
    assert answer.grader is Grader.SELF


async def test_another_users_question_cannot_be_answered(
    db: AsyncSession, user: User, other_user: User, notebook: Notebook
) -> None:
    from noema.core.errors import NotFound

    question = await make_question(db, user, notebook)
    with pytest.raises(NotFound):
        await answer_question(db, question.id, {"choice": 1}, owner_id=other_user.id)


async def test_answers_accumulate_as_an_append_only_log(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    question = await make_question(db, user, notebook)

    await answer_question(db, question.id, {"choice": 0}, owner_id=user.id)
    await answer_question(db, question.id, {"choice": 1}, owner_id=user.id)

    answers = (
        await db.scalars(select(Answer).where(Answer.question_id == question.id))
    ).all()
    assert len(answers) == 2
    assert {a.is_correct for a in answers} == {True, False}
