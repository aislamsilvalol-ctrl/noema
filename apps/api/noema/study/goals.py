"""Goals: what the learner needs to know, and by when.

The path is computed on every read rather than stored. A plan pinned at creation
describes a learner who no longer exists by Wednesday — the whole point of putting
a date on something is that the plan has to move underneath it.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.errors import NotFound
from noema.db.base import utcnow
from noema.db.models import (
    Concept,
    ConceptEdge,
    ConceptMastery,
    EdgeKind,
    Goal,
    Question,
)
from noema.engines.path import Path, Target, plan_path

__all__ = ["days_remaining", "path_for"]


def days_remaining(due_on: date, today: date | None = None) -> int:
    """Whole days left, today included.

    A goal due today has one day, not zero: there are still hours in it, and
    dividing the work by zero days would report every goal as impossible on its
    last morning.
    """
    return max((due_on - (today or utcnow().date())).days + 1, 1)


async def path_for(
    session: AsyncSession,
    goal_id: uuid.UUID,
    *,
    owner_id: uuid.UUID,
    today: date | None = None,
) -> tuple[Goal, Path]:
    """The goal and the plan as it stands right now."""
    goal = await session.scalar(
        select(Goal).where(Goal.id == goal_id, Goal.owner_id == owner_id)
    )
    if goal is None:
        raise NotFound("Goal not found")

    targets = await _targets(session, goal, owner_id)
    return goal, plan_path(
        targets,
        target_mastery=goal.target_mastery,
        days=days_remaining(goal.due_on, today),
        minutes_per_day=goal.minutes_per_day,
    )


async def _targets(
    session: AsyncSession, goal: Goal, owner_id: uuid.UUID
) -> list[Target]:
    """Every concept the notebook actually tests, with where the learner stands.

    Scoped by the questions and cards that exist rather than by every concept ever
    extracted: a concept with nothing to practise cannot be raised, and listing it
    as work to do would be a milestone with no way to reach it.
    """
    concept_ids = set(
        (
            await session.scalars(
                select(Question.concept_id).where(
                    Question.owner_id == owner_id,
                    Question.notebook_id == goal.notebook_id,
                    Question.concept_id.is_not(None),
                    Question.deleted_at.is_(None),
                )
            )
        ).all()
    )
    if not concept_ids:
        return []

    names = {
        row.id: row.name
        for row in (
            await session.scalars(
                select(Concept).where(
                    Concept.owner_id == owner_id, Concept.id.in_(concept_ids)
                )
            )
        ).all()
    }

    mastery = {
        concept_id: float(score)
        for concept_id, score in (
            await session.execute(
                select(ConceptMastery.concept_id, ConceptMastery.mastery).where(
                    ConceptMastery.owner_id == owner_id,
                    ConceptMastery.concept_id.in_(concept_ids),
                )
            )
        ).all()
    }

    edges = (
        await session.execute(
            select(ConceptEdge.src_id, ConceptEdge.dst_id).where(
                ConceptEdge.owner_id == owner_id,
                ConceptEdge.kind == EdgeKind.PREREQUISITE_OF,
                ConceptEdge.dst_id.in_(concept_ids),
            )
        )
    ).all()

    prerequisites: dict[uuid.UUID, set[uuid.UUID]] = {}
    for src, dst in edges:
        prerequisites.setdefault(dst, set()).add(src)

    return [
        Target(
            concept_id=concept_id,
            name=names.get(concept_id, "Unnamed concept"),
            # No mastery row means no evidence, which is not the same as zero
            # ability — but for planning it has to be treated as unlearned, or a
            # goal would call itself met on concepts nobody has ever practised.
            mastery=mastery.get(concept_id, 0.0),
            prerequisites=frozenset(prerequisites.get(concept_id, set())),
        )
        for concept_id in concept_ids
        if concept_id is not None
    ]


def achieved(goal: Goal, path: Path, now: datetime | None = None) -> datetime | None:
    """When a goal is done, which is when there is nothing left below target."""
    if goal.achieved_at is not None:
        return goal.achieved_at
    return (now or utcnow()) if not path.milestones else None
