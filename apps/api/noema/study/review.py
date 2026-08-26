"""Recording a review.

Three things happen, in this order and for this reason:

1. the evidence row is written — it is the only durable fact here;
2. the FSRS schedule is updated from it;
3. the mastery of the linked concept is recomputed.

Steps 2 and 3 are projections. If either is ever wrong, it can be rebuilt from step
1; if step 1 were lost, nothing could.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.errors import NotFound
from noema.core.logging import get_logger
from noema.db.base import utcnow
from noema.db.models import Card, CardSchedule, CardState, Review
from noema.engines import fsrs
from noema.study.mastery import recompute_for_review, recompute_mastery

log = get_logger(__name__)

__all__ = ["ReviewOutcome", "record_review"]

#: Cards introduced together would otherwise stay clumped forever, arriving as one
#: lump on the same day for years. A few percent of jitter breaks that up without
#: meaningfully moving anyone's retention.
FUZZ = 0.05

#: A failed card comes back inside the session rather than tomorrow.
RELEARN_DELAY = timedelta(minutes=10)


@dataclass(frozen=True, slots=True)
class ReviewOutcome:
    card_id: uuid.UUID
    due_at: datetime
    scheduled_days: float
    stability: float
    difficulty: float
    state: CardState
    mastery: float | None = None


async def record_review(
    session: AsyncSession,
    card_id: uuid.UUID,
    *,
    owner_id: uuid.UUID,
    rating: fsrs.Rating,
    elapsed_ms: int = 0,
    confidence: int | None = None,
    target_retention: float = 0.9,
    weights: fsrs.Weights = fsrs.DEFAULT_WEIGHTS,
    now: datetime | None = None,
) -> ReviewOutcome:
    """Grade a card and reschedule it.

    ``weights`` are the learner's own when enough history has earned them a fit,
    and the defaults otherwise — see `noema.study.scheduling`.
    """
    now = now or utcnow()

    card = await session.scalar(
        select(Card).where(
            Card.id == card_id,
            Card.owner_id == owner_id,
            Card.deleted_at.is_(None),
            # Every candidate-gathering and export query already excludes a
            # pending or suspended card (noema/study/session.py, sources.py's
            # dueCards route, exports.py) — this is the one place that actually
            # creates a schedule and evidence for a card, and it must enforce
            # the same rule at the source. Without it, POST /reviews accepted
            # any card_id the owner held, approved or not: a still-pending
            # AI-drafted card — one the learner never read, let alone
            # approved — could be scheduled and reviewed directly, which is
            # exactly what "drafted cards do not enter your rotation until you
            # have read them" (cards page) is supposed to prevent.
            Card.approved_at.is_not(None),
            Card.suspended_at.is_(None),
        )
    )
    if card is None:
        raise NotFound("Card not found")

    schedule = await session.scalar(
        select(CardSchedule).where(CardSchedule.card_id == card_id)
    )

    before = (
        fsrs.MemoryState(stability=schedule.stability, difficulty=schedule.difficulty)
        if schedule is not None and schedule.reps > 0
        else None
    )
    elapsed_days = _elapsed_days(schedule, now)
    after = fsrs.next_state(before, rating, elapsed_days, weights)

    if rating is fsrs.Rating.AGAIN:
        # Relearning: the card returns in minutes, and its stability is what decides
        # the interval only once it is answered correctly again.
        due_at = now + RELEARN_DELAY
        scheduled_days = RELEARN_DELAY.total_seconds() / 86400
        state = CardState.RELEARNING
    else:
        scheduled_days = _fuzzed(fsrs.interval_days(after, target_retention))
        due_at = now + timedelta(days=scheduled_days)
        state = CardState.REVIEW

    session.add(
        Review(
            owner_id=owner_id,
            card_id=card.id,
            concept_id=card.concept_id,
            rating=int(rating),
            state_before=_snapshot(before),
            state_after=_snapshot(after),
            elapsed_ms=max(elapsed_ms, 0),
            confidence=confidence,
            scheduled_days=scheduled_days,
            reviewed_at=now,
        )
    )

    if schedule is None:
        # Counters are set explicitly rather than left to the column defaults: those
        # only materialise at flush, and the increments below happen before it.
        schedule = CardSchedule(
            owner_id=owner_id,
            card_id=card.id,
            due_at=due_at,
            stability=after.stability,
            difficulty=after.difficulty,
            reps=0,
            lapses=0,
            state=CardState.NEW,
        )
        session.add(schedule)

    schedule.stability = after.stability
    schedule.difficulty = after.difficulty
    schedule.due_at = due_at
    schedule.last_review_at = now
    schedule.reps += 1
    schedule.lapses += 1 if rating is fsrs.Rating.AGAIN else 0
    schedule.state = state

    await session.flush()

    mastery = None
    if card.concept_id is not None:
        result = await recompute_mastery(
            session, card.concept_id, owner_id=owner_id, now=now
        )
        mastery = result.score if result else None
        # Concepts built on this one drew their prior from it, so their belief moved
        # too even though none of their cards were answered.
        await recompute_for_review(session, card.concept_id, owner_id=owner_id, now=now)

    log.info(
        "review.recorded",
        card_id=str(card.id),
        rating=int(rating),
        scheduled_days=round(scheduled_days, 2),
    )

    return ReviewOutcome(
        card_id=card.id,
        due_at=due_at,
        scheduled_days=scheduled_days,
        stability=after.stability,
        difficulty=after.difficulty,
        state=state,
        mastery=mastery,
    )


def _elapsed_days(schedule: CardSchedule | None, now: datetime) -> float:
    if schedule is None or schedule.last_review_at is None:
        return 0.0
    last = schedule.last_review_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    return max((now - last).total_seconds() / 86400, 0.0)


def _fuzzed(days: float) -> float:
    if days < 2.5:
        # Short intervals have no room to jitter without changing them materially.
        return days
    return days * random.uniform(1 - FUZZ, 1 + FUZZ)  # noqa: S311 — scheduling, not crypto


def _snapshot(state: fsrs.MemoryState | None) -> dict[str, float] | None:
    if state is None:
        return None
    return {"stability": state.stability, "difficulty": state.difficulty}
