"""Assembling candidates for the learning engine.

The engine is pure and knows nothing about the database. This is the layer that
gathers what the learner could do and estimates what each would cost — including
measuring their actual pace rather than assuming one.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.logging import get_logger
from noema.db.base import utcnow
from noema.db.models import (
    Card,
    CardSchedule,
    Concept,
    ConceptEdge,
    ConceptMastery,
    EdgeKind,
    Mistake,
    Question,
    Review,
)
from noema.engines import fsrs
from noema.engines.mastery import impact
from noema.engines.scheduler import Candidate, ItemKind, Plan, build_plan

log = get_logger(__name__)

__all__ = ["gather_candidates", "plan_session"]

#: Fallbacks until a learner has enough history to measure. Replaced per user as
#: soon as there is anything to measure from.
DEFAULT_COSTS: dict[ItemKind, float] = {
    ItemKind.CARD_REVIEW: 8.0,
    ItemKind.CARD_LEARN: 15.0,
    ItemKind.QUESTION: 45.0,
    ItemKind.MISCONCEPTION_DRILL: 90.0,
    ItemKind.PREREQ_REPAIR: 20.0,
    ItemKind.READ: 60.0,
}

#: Below this, a concept is weak enough to practise. From docs/mastery-engine.md §7.
WEAK_MASTERY = 60.0
MIN_EVIDENCE_FOR_WEAKNESS = 4.0

CANDIDATE_LIMIT = 300


async def plan_session(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    minutes: int,
    now: datetime | None = None,
) -> Plan:
    now = now or utcnow()
    candidates = await gather_candidates(session, owner_id=owner_id, now=now)
    backlog = await _overdue_count(session, owner_id, now)
    return build_plan(candidates, minutes, backlog=backlog)


async def gather_candidates(
    session: AsyncSession, *, owner_id: uuid.UUID, now: datetime
) -> list[Candidate]:
    """Everything the learner could usefully do right now."""
    pace = await _measured_pace(session, owner_id)
    importance = await _importance(session, owner_id)
    prerequisite_edges = await _prerequisite_map(session, owner_id)
    failing = await _failing_concepts(session, owner_id)
    mastery = await _mastery_by_concept(session, owner_id)
    last_seen = await _last_studied(session, owner_id, now)

    candidates: list[Candidate] = []
    candidates += await _due_cards(
        session,
        owner_id,
        now,
        pace,
        importance,
        prerequisite_edges,
        failing,
        mastery,
        last_seen,
    )
    candidates += await _new_cards(session, owner_id, pace, importance, last_seen)
    candidates += await _misconception_drills(session, owner_id, pace, importance)
    candidates += await _weak_questions(session, owner_id, pace, importance, last_seen)

    return candidates[:CANDIDATE_LIMIT]


async def _due_cards(
    session: AsyncSession,
    owner_id: uuid.UUID,
    now: datetime,
    pace: dict[ItemKind, float],
    importance: dict[uuid.UUID, float],
    prerequisite_edges: dict[uuid.UUID, frozenset[uuid.UUID]],
    failing: dict[uuid.UUID, str],
    mastery: dict[uuid.UUID, float],
    last_seen: dict[uuid.UUID, float],
) -> list[Candidate]:
    rows = (
        await session.execute(
            select(Card, CardSchedule, Concept.name)
            .join(CardSchedule, CardSchedule.card_id == Card.id)
            .outerjoin(Concept, Concept.id == Card.concept_id)
            .where(
                Card.owner_id == owner_id,
                Card.deleted_at.is_(None),
                Card.suspended_at.is_(None),
                Card.approved_at.is_not(None),
                CardSchedule.due_at <= now,
            )
            .order_by(CardSchedule.due_at)
            .limit(200)
        )
    ).all()

    candidates: list[Candidate] = []
    for card, schedule, concept_name in rows:
        elapsed = _days_since(schedule.last_review_at, now)
        state = fsrs.MemoryState(
            stability=max(schedule.stability, 0.01),
            difficulty=min(max(schedule.difficulty, 1.0), 10.0),
        )
        retrievability = fsrs.retrievability(state, elapsed)
        after = fsrs.next_state(state, fsrs.Rating.GOOD, elapsed)

        candidates.append(
            Candidate(
                ref_id=card.id,
                kind=ItemKind.CARD_REVIEW,
                cost_seconds=pace[ItemKind.CARD_REVIEW],
                memory_gain=_memory_gain(
                    retrievability, state.stability, after.stability
                ),
                importance=importance.get(card.concept_id, 1.0)
                if card.concept_id
                else 1.0,
                concept_id=card.concept_id,
                concept_name=concept_name or "",
                retrievability=retrievability,
                overdue_ratio=_overdue_ratio(schedule, now),
                blocks_failing_concept=bool(
                    card.concept_id
                    and prerequisite_edges.get(card.concept_id, frozenset())
                    & failing.keys()
                ),
                blocked_concept_name=_blocked_name(
                    prerequisite_edges.get(card.concept_id, frozenset())
                    if card.concept_id
                    else frozenset(),
                    failing,
                ),
                mastery=mastery.get(card.concept_id) if card.concept_id else None,
                hours_since_studied=last_seen.get(card.concept_id)
                if card.concept_id
                else None,
                prerequisite_of=prerequisite_edges.get(card.concept_id, frozenset())
                if card.concept_id
                else frozenset(),
            )
        )
    return candidates


async def _new_cards(
    session: AsyncSession,
    owner_id: uuid.UUID,
    pace: dict[ItemKind, float],
    importance: dict[uuid.UUID, float],
    last_seen: dict[uuid.UUID, float],
) -> list[Candidate]:
    rows = (
        await session.execute(
            select(Card, Concept.name)
            .outerjoin(CardSchedule, CardSchedule.card_id == Card.id)
            .outerjoin(Concept, Concept.id == Card.concept_id)
            .where(
                Card.owner_id == owner_id,
                Card.deleted_at.is_(None),
                Card.suspended_at.is_(None),
                Card.approved_at.is_not(None),
                CardSchedule.id.is_(None),
            )
            .limit(50)
        )
    ).all()

    return [
        Candidate(
            ref_id=card.id,
            kind=ItemKind.CARD_LEARN,
            cost_seconds=pace[ItemKind.CARD_LEARN],
            # A first exposure is worth a lot in principle and nothing if it is
            # never reviewed, so it sits below a due review rather than above it.
            memory_gain=0.30,
            importance=importance.get(card.concept_id, 1.0) if card.concept_id else 1.0,
            concept_id=card.concept_id,
            concept_name=name or "",
            retrievability=0.0,
            hours_since_studied=last_seen.get(card.concept_id)
            if card.concept_id
            else None,
        )
        for card, name in rows
    ]


async def _misconception_drills(
    session: AsyncSession,
    owner_id: uuid.UUID,
    pace: dict[ItemKind, float],
    importance: dict[uuid.UUID, float],
) -> list[Candidate]:
    """Questions the learner got wrong while sure they were right."""
    rows = (
        await session.execute(
            select(Mistake, Question, Concept.name)
            .join(Question, Question.id == Mistake.question_id)
            .outerjoin(Concept, Concept.id == Mistake.concept_id)
            .where(
                Mistake.owner_id == owner_id,
                Mistake.resolved_at.is_(None),
                Mistake.is_misconception.is_(True),
            )
            .order_by(Mistake.created_at.desc())
            .limit(20)
        )
    ).all()

    return [
        Candidate(
            ref_id=question.id,
            kind=ItemKind.MISCONCEPTION_DRILL,
            cost_seconds=pace[ItemKind.MISCONCEPTION_DRILL],
            memory_gain=0.6,
            importance=importance.get(mistake.concept_id, 1.5)
            if mistake.concept_id
            else 1.5,
            concept_id=mistake.concept_id,
            concept_name=name or "",
            is_misconception=True,
        )
        for mistake, question, name in rows
    ]


async def _weak_questions(
    session: AsyncSession,
    owner_id: uuid.UUID,
    pace: dict[ItemKind, float],
    importance: dict[uuid.UUID, float],
    last_seen: dict[uuid.UUID, float],
) -> list[Candidate]:
    """Questions on concepts the learner is measurably weak at."""
    rows = (
        await session.execute(
            select(Question, Concept.name, ConceptMastery.mastery)
            .join(Concept, Concept.id == Question.concept_id)
            .join(
                ConceptMastery,
                (ConceptMastery.concept_id == Concept.id)
                & (ConceptMastery.owner_id == owner_id),
            )
            .where(
                Question.owner_id == owner_id,
                Question.deleted_at.is_(None),
                ConceptMastery.mastery < WEAK_MASTERY,
                ConceptMastery.evidence_count >= MIN_EVIDENCE_FOR_WEAKNESS,
            )
            .order_by(ConceptMastery.mastery)
            .limit(40)
        )
    ).all()

    return [
        Candidate(
            ref_id=question.id,
            kind=ItemKind.QUESTION,
            cost_seconds=pace[ItemKind.QUESTION],
            # The weaker the concept, the more a correct answer tells us.
            memory_gain=0.4 * (1 - mastery / 100),
            importance=importance.get(question.concept_id, 1.0)
            if question.concept_id
            else 1.0,
            concept_id=question.concept_id,
            concept_name=name or "",
            hours_since_studied=last_seen.get(question.concept_id)
            if question.concept_id
            else None,
        )
        for question, name, mastery in rows
    ]


def _memory_gain(retrievability: float, stability: float, next_stability: float) -> float:
    """Expected long-run retention gained by reviewing now.

    Peaks around R = 0.5 and is tempered by how much the review actually moves
    stability: answering something at R = 0.99 wastes the time, and at R = 0.2 the
    card has already been forgotten and costs a relearn.
    """
    if next_stability <= 0:
        return 0.0
    return (
        retrievability
        * (1 - retrievability)
        * ((next_stability - stability) / next_stability)
    )


def _overdue_ratio(schedule: CardSchedule, now: datetime) -> float:
    if schedule.last_review_at is None:
        return 0.0
    due = _aware(schedule.due_at)
    last = _aware(schedule.last_review_at)
    interval = (due - last).total_seconds()
    if interval <= 0:
        return 0.0
    return max((now - last).total_seconds() / interval, 0.0)


async def _measured_pace(
    session: AsyncSession, owner_id: uuid.UUID
) -> dict[ItemKind, float]:
    """The learner's own median answer time, where there is enough history.

    Estimates get better the more the plan is used, which is the difference between
    a time budget that means something and one that is decoration.
    """
    pace = dict(DEFAULT_COSTS)

    rows = (
        await session.scalars(
            select(Review.elapsed_ms)
            .where(Review.owner_id == owner_id, Review.elapsed_ms > 0)
            .order_by(Review.reviewed_at.desc())
            .limit(200)
        )
    ).all()

    if len(rows) >= 10:
        # Clamped: a card left open over lunch should not convince the planner that
        # reviews take four minutes each.
        seconds = median(rows) / 1000
        pace[ItemKind.CARD_REVIEW] = min(max(seconds, 2.0), 60.0)
        pace[ItemKind.CARD_LEARN] = pace[ItemKind.CARD_REVIEW] * 1.8

    return pace


async def _importance(
    session: AsyncSession, owner_id: uuid.UUID
) -> dict[uuid.UUID, float]:
    """Graph-weighted importance per concept, from docs/mastery-engine.md §7."""
    # Rows are typed as Row[...] rather than plain tuples, so this is spelled out
    # instead of handed straight to dict().
    mastery: dict[uuid.UUID, float] = {
        row.concept_id: float(row.mastery)
        for row in (
            await session.execute(
                select(ConceptMastery.concept_id, ConceptMastery.mastery).where(
                    ConceptMastery.owner_id == owner_id
                )
            )
        ).all()
    }

    dependents: dict[uuid.UUID, set[uuid.UUID]] = {}
    for src, dst in (
        await session.execute(
            select(ConceptEdge.src_id, ConceptEdge.dst_id).where(
                ConceptEdge.owner_id == owner_id,
                ConceptEdge.kind == EdgeKind.PREREQUISITE_OF,
            )
        )
    ).all():
        dependents.setdefault(src, set()).add(dst)

    importance: dict[uuid.UUID, float] = {}
    for concept_id, score in mastery.items():
        direct = dependents.get(concept_id, set())
        second = {d for child in direct for d in dependents.get(child, set())}
        importance[concept_id] = impact(float(score), [len(direct), len(second)])

    return importance


async def _prerequisite_map(
    session: AsyncSession, owner_id: uuid.UUID
) -> dict[uuid.UUID, frozenset[uuid.UUID]]:
    edges: dict[uuid.UUID, set[uuid.UUID]] = {}
    for src, dst in (
        await session.execute(
            select(ConceptEdge.src_id, ConceptEdge.dst_id).where(
                ConceptEdge.owner_id == owner_id,
                ConceptEdge.kind == EdgeKind.PREREQUISITE_OF,
            )
        )
    ).all():
        edges.setdefault(src, set()).add(dst)
    return {src: frozenset(dsts) for src, dsts in edges.items()}


async def _failing_concepts(
    session: AsyncSession, owner_id: uuid.UUID
) -> dict[uuid.UUID, str]:
    """Concepts weak enough that their prerequisites are worth revisiting.

    Named, not just identified: the plan has to be able to say which concept kept
    slipping, and looking the name up again later would mean a second query for
    something already in hand.
    """
    rows = (
        await session.execute(
            select(ConceptMastery.concept_id, Concept.name)
            .join(Concept, Concept.id == ConceptMastery.concept_id)
            .where(
                ConceptMastery.owner_id == owner_id,
                ConceptMastery.mastery < WEAK_MASTERY,
                ConceptMastery.evidence_count >= MIN_EVIDENCE_FOR_WEAKNESS,
            )
        )
    ).all()
    return dict(rows)  # type: ignore[arg-type]


async def _mastery_by_concept(
    session: AsyncSession, owner_id: uuid.UUID
) -> dict[uuid.UUID, float]:
    rows = (
        await session.execute(
            select(ConceptMastery.concept_id, ConceptMastery.mastery).where(
                ConceptMastery.owner_id == owner_id
            )
        )
    ).all()
    return {concept_id: float(mastery) for concept_id, mastery in rows}


def _blocked_name(unblocks: frozenset[uuid.UUID], failing: dict[uuid.UUID, str]) -> str:
    """The failing concept this item is holding back, if any.

    One name rather than a list: a rationale that recites four concepts is a
    paragraph nobody reads, and the first is enough to make the point.
    """
    for concept_id in unblocks:
        name = failing.get(concept_id)
        if name:
            return name
    return ""


async def _last_studied(
    session: AsyncSession, owner_id: uuid.UUID, now: datetime
) -> dict[uuid.UUID, float]:
    rows = (
        await session.execute(
            select(Review.concept_id, func.max(Review.reviewed_at))
            .where(Review.owner_id == owner_id, Review.concept_id.is_not(None))
            .group_by(Review.concept_id)
        )
    ).all()

    return {
        concept_id: (now - _aware(moment)).total_seconds() / 3600
        for concept_id, moment in rows
        if concept_id is not None and moment is not None
    }


async def _overdue_count(
    session: AsyncSession, owner_id: uuid.UUID, now: datetime
) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(CardSchedule)
        .join(Card, Card.id == CardSchedule.card_id)
        .where(
            CardSchedule.owner_id == owner_id,
            CardSchedule.due_at <= now,
            Card.deleted_at.is_(None),
            Card.suspended_at.is_(None),
        )
    )
    return int(count or 0)


def _days_since(moment: datetime | None, now: datetime) -> float:
    if moment is None:
        return 0.0
    return max((now - _aware(moment)).total_seconds() / 86400, 0.0)


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def summarise(plan: Plan) -> dict[str, object]:
    """The stored shape of a plan, for replaying scheduler changes against outcomes."""
    return {
        "rationale": plan.rationale,
        "estimated_seconds": round(plan.estimated_seconds, 1),
        "blocks": [
            {
                "kind": block.kind.value,
                "why": block.why,
                "seconds": round(block.seconds, 1),
                "items": [
                    {
                        "ref_id": str(item.ref_id),
                        "kind": item.kind.value,
                        "concept_id": str(item.concept_id) if item.concept_id else None,
                    }
                    for item in block.items
                ],
            }
            for block in plan.blocks
        ],
    }


def horizon(days: int) -> datetime:
    return utcnow() + timedelta(days=days)
