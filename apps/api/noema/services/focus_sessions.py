"""Modo TDAH sittings: plan, steps, pause, resume, an end.

A focus session is the *shape* of a short sitting, never its content. The
content is the product's ordinary learning: a learn sitting is the same
lesson (`TeachingSession`) driven through `POST /ai/professor` with the focus
profile; a review sitting is the same due queue rated through `POST /reviews`.
So mastery, the student model, card schedules and XP move exactly as they do
in normal mode — this table cannot fork them because it never writes them.

Rules kept here:

- at most one active-or-paused sitting per learner (also a partial unique
  index; a race that slips past the read lands on the index and is answered
  with the sitting that won);
- a step is counted by its index, so a double click or a retried request
  counts once;
- time paused is not time spent: "time left" subtracts it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.errors import Conflict, NoemaError
from noema.db.base import utcnow
from noema.db.models import (
    FOCUS_OPEN,
    FocusSession,
    FocusStatus,
    LearningJourney,
    Review,
    StudentConceptState,
    TeachingSession,
)
from noema.db.repository import OwnedRepository
from noema.services.next_activity import (
    NextActivity,
    next_activity,
    review_minutes,
)

__all__ = [
    "DURATIONS",
    "MINUTES_PER_LEARN_STEP",
    "FocusSessions",
    "FocusSummary",
    "auto_minutes",
    "steps_for",
]

#: The durations offered; `None` is "Auto".
DURATIONS = (5, 10, 15, 25)
#: One learn micro-step: read a short chunk, answer one thing, see the verdict.
MINUTES_PER_LEARN_STEP = 2.5
#: Cards per minute in a review sitting (≈30 s a card, the planner's figure).
CARDS_PER_MINUTE = 2


class GoalRequired(NoemaError):
    slug = "goal-required"
    title = "Nothing to continue yet"


def auto_minutes(activity: NextActivity) -> int:
    """A duration from what is actually waiting, rounded to an offered one.

    Reviews: the shortest offered duration that holds the due cards, at most
    15. Learning: 10 — two to four micro-steps, the profile's own default.
    No "7.5 minutes": every answer is one of the buttons.
    """
    if activity.kind == "review":
        needed = review_minutes(activity.due_count)
        return next((m for m in DURATIONS[:3] if m >= needed), 15)
    return 10


def steps_for(kind: str, minutes: int, due_count: int = 0) -> int:
    if kind == "review":
        return max(1, min(due_count, minutes * CARDS_PER_MINUTE))
    return max(2, round(minutes / MINUTES_PER_LEARN_STEP))


@dataclass(frozen=True, slots=True)
class FocusSummary:
    """What the sitting did, read from the evidence tables."""

    cards_reviewed: int
    concepts_touched: list[str]


class FocusSessions:
    def __init__(self, db: AsyncSession, owner_id: uuid.UUID) -> None:
        self.db = db
        self.owner_id = owner_id
        self.rows = OwnedRepository(db, FocusSession, owner_id)

    async def current(self) -> FocusSession | None:
        found: FocusSession | None = await self.db.scalar(
            select(FocusSession)
            .where(
                FocusSession.owner_id == self.owner_id,
                FocusSession.status.in_(FOCUS_OPEN),
            )
            .limit(1)
        )
        return found

    async def get(self, focus_id: uuid.UUID) -> FocusSession:
        return await self.rows.get(focus_id)

    async def start(
        self,
        *,
        minutes: int | None,
        goal: str = "",
        learn_minutes: int = 10,
        now: datetime | None = None,
    ) -> FocusSession:
        """A new sitting from the next activity — or the open one, unchanged.

        Starting twice (a double tap, a second device) returns the sitting
        already under way rather than stacking a second one.
        """
        existing = await self.current()
        if existing is not None:
            return existing
        now = now or utcnow()
        activity = await next_activity(
            self.db, self.owner_id, learn_minutes=learn_minutes
        )
        goal = " ".join(goal.split())[:4000]
        if activity.kind == "start" and not goal:
            raise GoalRequired("Say what you want to learn to start a focus session.")

        kind = "review" if activity.kind == "review" else "learn"
        planned = minutes if minutes in DURATIONS else auto_minutes(activity)
        teaching_session_id = activity.session_id
        journey_id = activity.journey_id
        title = activity.title
        concept = activity.concept

        if kind == "learn" and teaching_session_id is None:
            # The lesson this sitting drives: the journey's own (a fresh
            # sitting of it), or, with nothing under way, a new lesson whose
            # goal is the learner's sentence — the engine turns it into a
            # journey on the first turn, exactly as in normal mode.
            journey = (
                await OwnedRepository(self.db, LearningJourney, self.owner_id).get(
                    journey_id
                )
                if journey_id is not None
                else None
            )
            lesson = TeachingSession(
                owner_id=self.owner_id,
                notebook_id=journey.notebook_id if journey else None,
                journey_id=journey.id if journey else None,
                learning_goal=journey.goal if journey else goal,
                subject=journey.subject if journey else "",
            )
            self.db.add(lesson)
            await self.db.flush()
            teaching_session_id = lesson.id
            if journey is None:
                title = goal[:200]

        row = FocusSession(
            owner_id=self.owner_id,
            kind=kind,
            journey_id=journey_id,
            teaching_session_id=teaching_session_id if kind == "learn" else None,
            title=title[:200],
            concept=concept[:200],
            planned_minutes=planned,
            steps_total=steps_for(kind, planned, activity.due_count),
            steps_done=0,
            status=FocusStatus.ACTIVE.value,
            started_at=now,
            last_activity_at=now,
            paused_seconds=0,
        )
        try:
            async with self.db.begin_nested():
                self.db.add(row)
        except IntegrityError:
            # Another request opened one between the read and this write.
            won = await self.current()
            if won is None:
                raise
            return won
        return row

    async def _open(self, focus_id: uuid.UUID) -> FocusSession:
        row = await self.get(focus_id)
        if row.status not in FOCUS_OPEN:
            raise Conflict("This focus session has already ended.")
        return row

    async def step(
        self, focus_id: uuid.UUID, *, index: int, now: datetime | None = None
    ) -> FocusSession:
        """Count step `index` (0-based) as done — once.

        An index already counted is a no-op (a retry, a double click); an
        index past the next one is refused rather than skipping steps.
        """
        row = await self._open(focus_id)
        if index < row.steps_done:
            return row
        if index > row.steps_done:
            raise Conflict(
                f"Step {index} is ahead of this session ({row.steps_done} done)."
            )
        now = now or utcnow()
        row.steps_done += 1
        row.last_activity_at = now
        if row.status == FocusStatus.PAUSED.value:
            self._unpause(row, now)
        await self.db.flush()
        return row

    def _unpause(self, row: FocusSession, now: datetime) -> None:
        if row.paused_at is not None:
            row.paused_seconds += max(0, int((now - row.paused_at).total_seconds()))
        row.paused_at = None
        row.status = FocusStatus.ACTIVE.value

    async def pause(
        self, focus_id: uuid.UUID, *, now: datetime | None = None
    ) -> FocusSession:
        row = await self._open(focus_id)
        if row.status == FocusStatus.PAUSED.value:
            return row
        now = now or utcnow()
        row.status = FocusStatus.PAUSED.value
        row.paused_at = now
        row.last_activity_at = now
        await self.db.flush()
        return row

    async def resume(
        self, focus_id: uuid.UUID, *, now: datetime | None = None
    ) -> FocusSession:
        row = await self._open(focus_id)
        now = now or utcnow()
        if row.status == FocusStatus.PAUSED.value:
            self._unpause(row, now)
        row.last_activity_at = now
        await self.db.flush()
        return row

    async def finish(
        self, focus_id: uuid.UUID, *, status: FocusStatus, now: datetime | None = None
    ) -> FocusSession:
        """Complete or abandon. Ending an ended sitting the same way is a no-op."""
        row = await self.get(focus_id)
        if row.status == status.value:
            return row
        if row.status not in FOCUS_OPEN:
            raise Conflict("This focus session has already ended.")
        now = now or utcnow()
        if row.status == FocusStatus.PAUSED.value:
            self._unpause(row, now)
        row.status = status.value
        row.completed_at = now
        row.last_activity_at = now
        await self.db.flush()
        return row

    async def journey_of(self, row: FocusSession) -> uuid.UUID | None:
        """The journey, learned late for a sitting that started a new subject."""
        if row.journey_id is not None or row.teaching_session_id is None:
            return row.journey_id
        journey_id: uuid.UUID | None = await self.db.scalar(
            select(TeachingSession.journey_id).where(
                TeachingSession.id == row.teaching_session_id,
                TeachingSession.owner_id == self.owner_id,
            )
        )
        if journey_id is not None:
            row.journey_id = journey_id
            await self.db.flush()
        return journey_id

    async def summary(
        self, row: FocusSession, *, now: datetime | None = None
    ) -> FocusSummary:
        end = row.completed_at or now or utcnow()
        cards = int(
            await self.db.scalar(
                select(func.count())
                .select_from(Review)
                .where(
                    Review.owner_id == self.owner_id,
                    Review.reviewed_at >= row.started_at,
                    Review.reviewed_at <= end,
                )
            )
            or 0
        )
        journey_id = await self.journey_of(row)
        concepts: list[str] = []
        if journey_id is not None:
            concepts = list(
                (
                    await self.db.scalars(
                        select(StudentConceptState.name)
                        .where(
                            StudentConceptState.owner_id == self.owner_id,
                            StudentConceptState.journey_id == journey_id,
                            StudentConceptState.last_evidence_at >= row.started_at,
                        )
                        .order_by(StudentConceptState.last_evidence_at)
                        .limit(6)
                    )
                ).all()
            )
        return FocusSummary(cards_reviewed=cards, concepts_touched=concepts)
