"""Exam mode.

The properties that make an exam an exam, rather than a quiz with a clock: the
paper does not change once it starts, an unanswered question counts against you,
handing in twice is refused, and the result says which concepts went wrong rather
than only how many.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.errors import Conflict
from noema.db.base import utcnow
from noema.db.models import (
    Concept,
    Difficulty,
    Notebook,
    Question,
    QuestionType,
    Subject,
    User,
    Workspace,
)
from noema.db.repository import OwnedRepository
from noema.study.exam import grade_exam, start_exam

pytestmark = pytest.mark.asyncio


async def build(db: AsyncSession, owner: User) -> tuple[Notebook, list[Question]]:
    workspace = await OwnedRepository(db, Workspace, owner.id).create(
        title="Medicine", slug=f"med-{uuid.uuid4().hex[:8]}"
    )
    subject = await OwnedRepository(db, Subject, owner.id).create(
        workspace_id=workspace.id, title="Physiology", slug="phys"
    )
    notebook = await OwnedRepository(db, Notebook, owner.id).create(
        subject_id=subject.id, title="Cardio", slug="cardio", retrieval_settings={}
    )

    concepts = [
        await OwnedRepository(db, Concept, owner.id).create(
            workspace_id=workspace.id,
            name=name,
            normalized_name=name.lower(),
            definition="",
        )
        for name in ("Preload", "Afterload")
    ]

    questions = []
    for i, concept in enumerate(concepts * 2):
        questions.append(
            await OwnedRepository(db, Question, owner.id).create(
                notebook_id=notebook.id,
                concept_id=concept.id,
                type=QuestionType.TRUE_FALSE,
                difficulty=Difficulty.MEDIUM,
                prompt=f"Statement {i}",
                payload={"answer": True, "explanation": "because"},
            )
        )
    return notebook, questions


async def test_the_paper_is_fixed_when_it_starts(db: AsyncSession, user: User) -> None:
    """Adding a question mid-exam must not change what is being sat."""
    notebook, _ = await build(db, user)
    exam = await start_exam(db, notebook.id, owner_id=user.id, count=4, minutes=20)
    before = list(exam.question_ids)

    await OwnedRepository(db, Question, user.id).create(
        notebook_id=notebook.id,
        concept_id=None,
        type=QuestionType.TRUE_FALSE,
        difficulty=Difficulty.EASY,
        prompt="Added later",
        payload={"answer": False},
    )

    assert list(exam.question_ids) == before
    assert len(before) == 4


async def test_an_unanswered_question_counts_against_you(
    db: AsyncSession, user: User
) -> None:
    """Dropping blanks from the denominator would flatter the score."""
    notebook, _ = await build(db, user)
    exam = await start_exam(db, notebook.id, owner_id=user.id, count=4, minutes=20)

    answered = uuid.UUID(str(exam.question_ids[0]))
    graded = await grade_exam(db, exam.id, {answered: {"answer": True}}, owner_id=user.id)

    assert graded.score == pytest.approx(0.25), (
        "one right out of four sat should be a quarter, not full marks for the "
        "only one attempted"
    )


async def test_the_result_says_which_concepts_went_wrong(
    db: AsyncSession, user: User
) -> None:
    """A mark is not actionable; a list of concepts is."""
    notebook, _ = await build(db, user)
    exam = await start_exam(db, notebook.id, owner_id=user.id, count=4, minutes=20)

    # Every question in this notebook is "true"; answering false everywhere makes
    # the whole paper wrong, and every concept should show up as such.
    responses = {uuid.UUID(str(qid)): {"answer": False} for qid in exam.question_ids}
    graded = await grade_exam(db, exam.id, responses, owner_id=user.id)

    concepts = graded.results["concepts"]
    assert concepts, "the result carried no concept breakdown"
    assert all(c["correct"] == 0 for c in concepts)
    assert sum(c["total"] for c in concepts) == 4, "the totals do not add up to the paper"
    # Weakest first, so the top of the list is where the work is.
    assert concepts == sorted(concepts, key=lambda c: c["score"])


async def test_handing_in_twice_is_refused(db: AsyncSession, user: User) -> None:
    """Otherwise a second submission is a free retake with the same paper."""
    notebook, _ = await build(db, user)
    exam = await start_exam(db, notebook.id, owner_id=user.id, count=3, minutes=20)
    await grade_exam(db, exam.id, {}, owner_id=user.id)

    with pytest.raises(Conflict):
        await grade_exam(db, exam.id, {}, owner_id=user.id)


async def test_late_is_recorded_not_refused(db: AsyncSession, user: User) -> None:
    """Losing someone's work to a clock is worse than an untimed result."""
    notebook, _ = await build(db, user)
    exam = await start_exam(db, notebook.id, owner_id=user.id, count=3, minutes=10)

    graded = await grade_exam(
        db, exam.id, {}, owner_id=user.id, now=utcnow() + timedelta(minutes=30)
    )

    assert graded.overtime is True
    assert graded.submitted_at is not None, "the work was thrown away"


async def test_an_empty_notebook_cannot_be_examined(db: AsyncSession, user: User) -> None:
    """Better a clear refusal than a zero-question exam that scores 0%."""
    workspace = await OwnedRepository(db, Workspace, user.id).create(
        title="Empty", slug=f"empty-{uuid.uuid4().hex[:8]}"
    )
    subject = await OwnedRepository(db, Subject, user.id).create(
        workspace_id=workspace.id, title="Nothing", slug="nothing"
    )
    notebook = await OwnedRepository(db, Notebook, user.id).create(
        subject_id=subject.id, title="Bare", slug="bare", retrieval_settings={}
    )

    with pytest.raises(Conflict):
        await start_exam(db, notebook.id, owner_id=user.id, count=5, minutes=10)
