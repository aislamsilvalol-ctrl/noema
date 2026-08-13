"""Exam mode: a fixed set of questions, timed, graded only at the end.

What separates this from a quiz is not the timer. It is that nothing comes back
until everything is handed in — no per-question verdict to correct course from,
no hints, no retry. That is the point: an exam measures what you can retrieve
unaided, and the moment it tells you how you are doing it stops measuring that.

The result is per concept rather than a mark. "62%" tells a learner nothing they
can act on; "you lost most of it on pre-load and clearance" does.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.errors import Conflict, NotFound
from noema.db.base import utcnow
from noema.db.models import Answer, Concept, Exam, Question
from noema.providers.gateway import AIGateway
from noema.study.questions import answer_question

__all__ = ["ConceptResult", "grade_exam", "start_exam"]

#: A minute of slack for the request itself. Being marked late because the submit
#: took two seconds is the kind of unfairness that makes people stop trusting a
#: tool.
GRACE = timedelta(seconds=60)


@dataclass(frozen=True, slots=True)
class ConceptResult:
    concept_id: uuid.UUID | None
    name: str
    correct: int
    total: int
    score: float


async def start_exam(
    session: AsyncSession,
    notebook_id: uuid.UUID,
    *,
    owner_id: uuid.UUID,
    count: int,
    minutes: int,
) -> Exam:
    """Fix a set of questions and start the clock.

    Questions are chosen at random from the notebook rather than by difficulty or
    weakness. An exam that quietly asks you what you are worst at is a drill; the
    number it produces is not comparable with the last one.
    """
    ids = (
        await session.scalars(
            select(Question.id)
            .where(
                Question.owner_id == owner_id,
                Question.notebook_id == notebook_id,
                Question.deleted_at.is_(None),
            )
            .order_by(func.random())
            .limit(count)
        )
    ).all()

    if not ids:
        raise Conflict(
            "This notebook has no questions yet. Generate some before sitting an exam."
        )

    exam = Exam(
        owner_id=owner_id,
        notebook_id=notebook_id,
        minutes=minutes,
        question_ids=[str(i) for i in ids],
        started_at=utcnow(),
    )
    session.add(exam)
    await session.flush()
    return exam


async def grade_exam(
    session: AsyncSession,
    exam_id: uuid.UUID,
    responses: dict[uuid.UUID, dict[str, Any]],
    *,
    owner_id: uuid.UUID,
    gateway: AIGateway | None = None,
    model: str | None = None,
    now: datetime | None = None,
) -> Exam:
    """Grade every question in one pass and record the outcome per concept.

    Unanswered questions are graded, not skipped: leaving one blank is a result,
    and dropping it from the denominator would flatter the score.
    """
    now = now or utcnow()

    exam = await session.scalar(
        select(Exam).where(Exam.id == exam_id, Exam.owner_id == owner_id)
    )
    if exam is None:
        raise NotFound("Exam not found")
    if exam.submitted_at is not None:
        # Re-grading would let someone improve a mark by submitting twice.
        raise Conflict("This exam has already been handed in.")

    answers: list[Answer] = []
    for raw in exam.question_ids:
        question_id = uuid.UUID(str(raw))
        answers.append(
            await answer_question(
                session,
                question_id,
                responses.get(question_id, {}),
                owner_id=owner_id,
                gateway=gateway,
                model=model,
                now=now,
            )
        )

    exam.submitted_at = now
    exam.overtime = now > exam.started_at + timedelta(minutes=exam.minutes) + GRACE
    exam.score = sum(a.score for a in answers) / len(answers) if answers else 0.0
    exam.results = {
        "concepts": [
            {
                "concept_id": str(r.concept_id) if r.concept_id else None,
                "name": r.name,
                "correct": r.correct,
                "total": r.total,
                "score": round(r.score, 3),
            }
            for r in await _by_concept(session, answers, owner_id=owner_id)
        ]
    }
    await session.flush()
    return exam


async def _by_concept(
    session: AsyncSession, answers: list[Answer], *, owner_id: uuid.UUID
) -> list[ConceptResult]:
    """Group the answers by what they were testing, weakest first."""
    buckets: dict[uuid.UUID | None, list[Answer]] = {}
    for answer in answers:
        buckets.setdefault(answer.concept_id, []).append(answer)

    named = {
        row.id: row.name
        for row in (
            await session.scalars(
                select(Concept).where(
                    Concept.owner_id == owner_id,
                    Concept.id.in_([k for k in buckets if k is not None]),
                )
            )
        ).all()
    }

    results = [
        ConceptResult(
            concept_id=concept_id,
            # A question with no concept attached still has to appear somewhere,
            # or the totals will not add up to what was sat.
            name=named.get(concept_id, "Unlinked questions")
            if concept_id
            else "Unlinked questions",
            correct=sum(1 for a in group if a.is_correct),
            total=len(group),
            score=sum(a.score for a in group) / len(group),
        )
        for concept_id, group in buckets.items()
    ]
    return sorted(results, key=lambda r: r.score)
