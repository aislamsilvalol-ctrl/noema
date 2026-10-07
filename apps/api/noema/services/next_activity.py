"""The next activity: one answer to "what do I do now?".

Deterministic and small on purpose. Three possible answers, in this order:

1. **review** — when cards are due and either enough of them have piled up
   (`REVIEW_THRESHOLD`) or one of them is overdue by more than a day. Memory
   that is fading is the cheapest thing to save and the most expensive to lose.
   (A few due cards with nothing else under way are also the next thing.)
2. **learn** — otherwise, continue the journey the learner was last on, at its
   current concept (and in its open lesson, when there is one).
3. **start** — nothing under way: start something.

`choose` is pure — counts and a candidate in, a decision out — so the rule is
tested without a database. `next_activity` reads the counts and the candidate
from the same tables the rest of the product uses (the `/cards?due=true` query,
the latest active journey) and hands them to it.

`reason` is a short sentence built only from those numbers; `reason_code` and
the counts let a client say the same thing in its own language.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.base import utcnow
from noema.db.models import (
    Card,
    CardSchedule,
    JourneyStatus,
    LearningJourney,
    TeachingSession,
)

__all__ = [
    "LEARN_MINUTES",
    "OVERDUE_AFTER",
    "REVIEW_THRESHOLD",
    "SECONDS_PER_CARD",
    "LearnCandidate",
    "NextActivity",
    "choose",
    "next_activity",
]

#: This many due cards are worth a sitting of their own.
REVIEW_THRESHOLD = 5
#: A card due for longer than this is overdue: reviewed first, whatever the count.
OVERDUE_AFTER = timedelta(days=1)
#: The planner's own figure for one review (see `today/page.tsx`, ≈30 s a card).
SECONDS_PER_CARD = 30
#: A learning sitting, when the learner has said nothing else.
LEARN_MINUTES = 10


@dataclass(frozen=True, slots=True)
class LearnCandidate:
    journey_id: uuid.UUID
    subject: str
    concept: str
    session_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class NextActivity:
    kind: str  # review · learn · start
    title: str
    concept: str
    journey_id: uuid.UUID | None
    session_id: uuid.UUID | None
    due_count: int
    overdue_count: int
    minutes_estimate: int
    reason_code: str  # overdue · due · continue · start
    reason: str

    def public(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "title": self.title,
            "concept": self.concept,
            "journey_id": self.journey_id,
            "session_id": self.session_id,
            "due_count": self.due_count,
            "overdue_count": self.overdue_count,
            "minutes_estimate": self.minutes_estimate,
            "reason_code": self.reason_code,
            "reason": self.reason,
        }


def review_minutes(due_count: int) -> int:
    """Whole minutes for this many cards, never less than one."""
    return max(1, round(due_count * SECONDS_PER_CARD / 60))


def _cards(n: int) -> str:
    return f"{n} card{'s' if n != 1 else ''}"


def choose(
    *,
    due_count: int,
    overdue_count: int,
    candidate: LearnCandidate | None,
    learn_minutes: int = LEARN_MINUTES,
    threshold: int = REVIEW_THRESHOLD,
) -> NextActivity:
    """The rule, with nothing read from anywhere."""
    pressing = due_count > 0 and (overdue_count > 0 or due_count >= threshold)
    # A few due cards and nothing else under way: those are still the next thing.
    if pressing or (due_count > 0 and candidate is None):
        overdue = overdue_count > 0
        reason = (
            f"{_cards(overdue_count)} overdue since yesterday or earlier"
            if overdue
            else f"{_cards(due_count)} due for review"
        )
        return NextActivity(
            kind="review",
            title=f"{_cards(due_count)} to review",
            concept="",
            journey_id=None,
            session_id=None,
            due_count=due_count,
            overdue_count=overdue_count,
            minutes_estimate=review_minutes(due_count),
            reason_code="overdue" if overdue else "due",
            reason=reason,
        )
    if candidate is not None:
        concept = candidate.concept or candidate.subject
        return NextActivity(
            kind="learn",
            title=candidate.subject or concept,
            concept=concept,
            journey_id=candidate.journey_id,
            session_id=candidate.session_id,
            due_count=due_count,
            overdue_count=overdue_count,
            minutes_estimate=learn_minutes,
            reason_code="continue",
            reason=f"Where you stopped in {candidate.subject or concept}",
        )
    return NextActivity(
        kind="start",
        title="",
        concept="",
        journey_id=None,
        session_id=None,
        due_count=due_count,
        overdue_count=overdue_count,
        minutes_estimate=learn_minutes,
        reason_code="start",
        reason="Nothing under way yet",
    )


def _due_clause(now: datetime) -> Any:
    return (CardSchedule.due_at.is_(None)) | (CardSchedule.due_at <= now)


async def due_counts(
    db: AsyncSession, owner_id: uuid.UUID, *, now: datetime | None = None
) -> tuple[int, int]:
    """(due, overdue) with exactly the `/cards?due=true` definition of due."""
    now = now or utcnow()
    base = (
        select(func.count())
        .select_from(Card)
        .outerjoin(CardSchedule, CardSchedule.card_id == Card.id)
        .where(
            Card.owner_id == owner_id,
            Card.deleted_at.is_(None),
            Card.approved_at.is_not(None),
            Card.suspended_at.is_(None),
        )
    )
    due = int(await db.scalar(base.where(_due_clause(now))) or 0)
    overdue = int(
        await db.scalar(base.where(CardSchedule.due_at <= now - OVERDUE_AFTER)) or 0
    )
    return due, overdue


async def learn_candidate(db: AsyncSession, owner_id: uuid.UUID) -> LearnCandidate | None:
    """The journey the learner was last on, and its newest open lesson."""
    journey = await db.scalar(
        select(LearningJourney)
        .where(
            LearningJourney.owner_id == owner_id,
            LearningJourney.status == JourneyStatus.ACTIVE.value,
        )
        .order_by(LearningJourney.last_active_at.desc().nulls_last())
        .limit(1)
    )
    if journey is None:
        return None
    session_id = await db.scalar(
        select(TeachingSession.id)
        .where(
            TeachingSession.owner_id == owner_id,
            TeachingSession.journey_id == journey.id,
            TeachingSession.ended_at.is_(None),
        )
        .order_by(TeachingSession.last_turn_at.desc().nulls_last())
        .limit(1)
    )
    return LearnCandidate(
        journey_id=journey.id,
        subject=journey.subject,
        concept=journey.current_concept,
        session_id=session_id,
    )


async def next_activity(
    db: AsyncSession,
    owner_id: uuid.UUID,
    *,
    learn_minutes: int = LEARN_MINUTES,
    now: datetime | None = None,
) -> NextActivity:
    due, overdue = await due_counts(db, owner_id, now=now)
    return choose(
        due_count=due,
        overdue_count=overdue,
        candidate=await learn_candidate(db, owner_id),
        learn_minutes=learn_minutes,
    )
