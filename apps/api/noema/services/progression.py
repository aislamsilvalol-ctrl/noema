"""Progression: XP, levels, missions and marks, earned only from learning.

The engine reads the evidence the learning system already keeps and never
the client: a review graded, a concept that reached "mastered", a checkpoint
submitted, a planned session completed, a day with real lesson work. Each
becomes at most one `XpEvent`, keyed on its source, so reading the same
evidence again (a refresh, a retry, two tabs) earns nothing.

Nothing in the learning code calls this. It reads after the fact, which keeps
teaching and scoring separate: a bug here can never change what a lesson
does, and a change to the economy can be replayed over the evidence.

The economy, in one place (tuned by hand; to be checked against real use):

    review            10 recalled · 6 hard · 3 forgotten — the first review
                      of each card per day only, so cramming one card pays once
    concept mastered  100, once per concept per journey
    checkpoint        40 + up to 60 for the score · micro-check 10 + up to 20
    planned session   30, at most three a day
    learning day      20 for a day with three or more lesson turns
    daily mission     25 each · weekly mission 100 each (granted automatically)
    mark              50 each

Levels climb a curve, fast at first and slower later:
`xp_for_level(n) = round(60 * (n - 1) ** 1.55)` — level 2 at 60 XP, 5 at
515, 10 at about 1,800, 20 at about 5,700. A level is product progress, not a
measure of anyone: it says how much learning happened here, not how clever
the learner is. Mastery of a subject lives on the knowledge map, apart.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import (
    Assessment,
    ConceptState,
    JourneyStatus,
    LearningJourney,
    MasteryEvent,
    Review,
    StudentConceptState,
    StudySession,
    TeachingTurn,
    TurnRole,
    XpEvent,
)

REVIEW_XP = {1: 3, 2: 6, 3: 10, 4: 10}
MASTERED_XP = 100
SESSION_XP = 30
SESSIONS_PER_DAY = 3
LEARNING_DAY_XP = 20
LEARNING_DAY_TURNS = 3
DAILY_MISSION_XP = 25
WEEKLY_MISSION_XP = 100
MARK_XP = 50

#: Kinds that are learning itself, as opposed to rewards for it.
LEARNING_KINDS = ("review", "concept_mastered", "checkpoint", "session", "learning_day")
CHECK_KINDS = ("quiz", "check", "assessment", "flashcard", "teach_back")

STAGES = (
    (35, "horizon"),
    (20, "altitude"),
    (10, "crossing"),
    (5, "trail"),
    (1, "first_steps"),
)


def xp_for_level(level: int) -> int:
    return round(60 * math.pow(max(level - 1, 0), 1.55))


def level_for(xp: int) -> int:
    level = 1
    while xp_for_level(level + 1) <= xp:
        level += 1
    return level


def stage_for(level: int) -> str:
    return next(name for floor, name in STAGES if level >= floor)


def zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


@dataclass(frozen=True, slots=True)
class Mission:
    id: str
    period: str  # daily · weekly
    progress: int
    target: int
    xp: int
    ends_at: datetime

    @property
    def done(self) -> bool:
        return self.progress >= self.target


@dataclass(frozen=True, slots=True)
class Mark:
    id: str
    earned: bool
    earned_at: datetime | None


@dataclass(slots=True)
class Summary:
    level: int
    stage: str
    xp_total: int
    level_floor: int
    next_level_at: int
    xp_today: int
    missions: list[Mission] = field(default_factory=list)
    marks: list[Mark] = field(default_factory=list)


MARKS = (
    "first_lesson",
    "first_mastered",
    "first_checkpoint",
    "week_streak",
    "ten_mastered",
    "hundred_recalls",
    "path_complete",
)


class ProgressionEngine:
    def __init__(
        self, db: AsyncSession, owner_id: uuid.UUID, tz: str | None = None
    ) -> None:
        self.db = db
        self.owner_id = owner_id
        self.tz = zone(tz)

    # ── Earning ──────────────────────────────────────────────────────────

    async def sync(self, *, now: datetime | None = None) -> None:
        """Turn any new evidence into XP. Idempotent by construction."""
        now = now or datetime.now(UTC)
        rows: list[dict[str, Any]] = []
        rows += await self._reviews()
        rows += await self._mastered()
        rows += await self._checkpoints()
        rows += await self._sessions()
        rows += await self._learning_days()
        await self._insert(rows)
        # Missions and marks read the XP just written, so they come second.
        missions = await self.missions(now=now)
        await self._insert(
            [
                self._row(
                    "mission",
                    f"{m.period}:{m.id}:{self._period_key(m.period, now)}",
                    m.xp,
                    now,
                    {"mission": m.id},
                )
                for m in missions
                if m.done
            ]
        )
        await self._insert(
            [
                self._row("mark", mark_id, MARK_XP, earned_at, {})
                for mark_id, earned_at in (await self._earned_marks()).items()
            ]
        )

    def _row(
        self, kind: str, source_id: str, xp: int, at: datetime, detail: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "id": uuid.uuid4(),
            "owner_id": self.owner_id,
            "kind": kind,
            "source_id": source_id[:160],
            "xp": xp,
            "occurred_at": at,
            "detail": detail,
        }

    async def _insert(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        await self.db.execute(
            insert(XpEvent)
            .values(rows)
            .on_conflict_do_nothing(constraint="uq_xp_events_source")
        )

    async def _reviews(self) -> list[dict[str, Any]]:
        # The first review of each card on each (UTC) day. The day is the
        # server's, not the client's, so a changed time zone cannot mint a
        # second "first review" for the same card.
        day = func.date(func.timezone("UTC", Review.reviewed_at))
        query = (
            select(Review.card_id, day.label("day"), Review.rating, Review.reviewed_at)
            .where(Review.owner_id == self.owner_id)
            .distinct(Review.card_id, day)
            .order_by(Review.card_id, day, Review.reviewed_at)
        )
        return [
            self._row(
                "review",
                f"{row.card_id}:{row.day}",
                REVIEW_XP.get(int(row.rating), 3),
                row.reviewed_at,
                {"rating": int(row.rating)},
            )
            for row in await self.db.execute(query)
        ]

    async def _mastered(self) -> list[dict[str, Any]]:
        query = select(
            StudentConceptState.id,
            StudentConceptState.name,
            StudentConceptState.updated_at,
        ).where(
            StudentConceptState.owner_id == self.owner_id,
            StudentConceptState.state == ConceptState.MASTERED.value,
        )
        return [
            self._row(
                "concept_mastered",
                str(row.id),
                MASTERED_XP,
                row.updated_at,
                {"concept": row.name},
            )
            for row in await self.db.execute(query)
        ]

    async def _checkpoints(self) -> list[dict[str, Any]]:
        query = select(
            Assessment.id, Assessment.kind, Assessment.score, Assessment.submitted_at
        ).where(
            Assessment.owner_id == self.owner_id, Assessment.submitted_at.is_not(None)
        )
        rows = []
        for row in await self.db.execute(query):
            score = max(0.0, min(float(row.score or 0.0), 1.0))
            xp = (
                40 + round(60 * score)
                if row.kind == "checkpoint"
                else 10 + round(20 * score)
            )
            rows.append(
                self._row(
                    "checkpoint", str(row.id), xp, row.submitted_at, {"kind": row.kind}
                )
            )
        return rows

    async def _sessions(self) -> list[dict[str, Any]]:
        query = (
            select(StudySession.id, StudySession.completed_at)
            .where(
                StudySession.owner_id == self.owner_id,
                StudySession.completed_at.is_not(None),
            )
            .order_by(StudySession.completed_at)
        )
        per_day: dict[date, int] = {}
        rows = []
        for row in await self.db.execute(query):
            day = row.completed_at.astimezone(UTC).date()
            per_day[day] = per_day.get(day, 0) + 1
            if per_day[day] <= SESSIONS_PER_DAY:
                rows.append(
                    self._row("session", str(row.id), SESSION_XP, row.completed_at, {})
                )
        return rows

    async def _learning_days(self) -> list[dict[str, Any]]:
        day = func.date(func.timezone("UTC", TeachingTurn.created_at))
        query = (
            select(
                day.label("day"),
                func.count().label("turns"),
                func.min(TeachingTurn.created_at),
            )
            .where(
                TeachingTurn.owner_id == self.owner_id,
                TeachingTurn.role == TurnRole.LEARNER,
            )
            .group_by(day)
            .having(func.count() >= LEARNING_DAY_TURNS)
        )
        return [
            self._row(
                "learning_day",
                str(row.day),
                LEARNING_DAY_XP,
                row[2],
                {"turns": row.turns},
            )
            for row in await self.db.execute(query)
        ]

    # ── Missions ─────────────────────────────────────────────────────────

    def _day_window(self, now: datetime) -> tuple[datetime, datetime]:
        local = now.astimezone(self.tz)
        start = datetime(local.year, local.month, local.day, tzinfo=self.tz)
        return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)

    def _week_window(self, now: datetime) -> tuple[datetime, datetime]:
        day_start, _ = self._day_window(now)
        local = day_start.astimezone(self.tz)
        start = local - timedelta(days=local.weekday())
        return start.astimezone(UTC), (start + timedelta(days=7)).astimezone(UTC)

    def _period_key(self, period: str, now: datetime) -> str:
        local = now.astimezone(self.tz)
        if period == "daily":
            return local.date().isoformat()
        year, week, _ = local.isocalendar()
        return f"{year}-W{week:02d}"

    async def _count_xp(
        self, kinds: tuple[str, ...], start: datetime, end: datetime
    ) -> int:
        count = await self.db.scalar(
            select(func.count())
            .select_from(XpEvent)
            .where(
                XpEvent.owner_id == self.owner_id,
                XpEvent.kind.in_(kinds),
                XpEvent.occurred_at >= start,
                XpEvent.occurred_at < end,
            )
        )
        return int(count or 0)

    async def _learner_turns(self, start: datetime, end: datetime) -> int:
        count = await self.db.scalar(
            select(func.count())
            .select_from(TeachingTurn)
            .where(
                TeachingTurn.owner_id == self.owner_id,
                TeachingTurn.role == TurnRole.LEARNER,
                TeachingTurn.created_at >= start,
                TeachingTurn.created_at < end,
            )
        )
        return int(count or 0)

    async def _checks(self, start: datetime, end: datetime) -> int:
        count = await self.db.scalar(
            select(func.count())
            .select_from(MasteryEvent)
            .where(
                MasteryEvent.owner_id == self.owner_id,
                MasteryEvent.kind.in_(CHECK_KINDS),
                MasteryEvent.created_at >= start,
                MasteryEvent.created_at < end,
            )
        )
        return int(count or 0)

    async def _active_days(self, start: datetime, end: datetime) -> int:
        local_day = func.date(func.timezone(str(self.tz), XpEvent.occurred_at))
        count = await self.db.scalar(
            select(func.count(func.distinct(local_day))).where(
                XpEvent.owner_id == self.owner_id,
                XpEvent.kind.in_(LEARNING_KINDS),
                XpEvent.occurred_at >= start,
                XpEvent.occurred_at < end,
            )
        )
        return int(count or 0)

    async def missions(self, *, now: datetime | None = None) -> list[Mission]:
        now = now or datetime.now(UTC)
        d0, d1 = self._day_window(now)
        w0, w1 = self._week_window(now)
        turns_today = await self._learner_turns(d0, d1)
        sessions_today = await self._count_xp(("session",), d0, d1)
        return [
            Mission(
                "recall",
                "daily",
                min(await self._count_xp(("review",), d0, d1), 3),
                3,
                DAILY_MISSION_XP,
                d1,
            ),
            Mission(
                "lesson",
                "daily",
                1 if turns_today >= LEARNING_DAY_TURNS or sessions_today else 0,
                1,
                DAILY_MISSION_XP,
                d1,
            ),
            Mission(
                "check",
                "daily",
                min(await self._checks(d0, d1), 1),
                1,
                DAILY_MISSION_XP,
                d1,
            ),
            Mission(
                "days",
                "weekly",
                min(await self._active_days(w0, w1), 4),
                4,
                WEEKLY_MISSION_XP,
                w1,
            ),
            Mission(
                "master",
                "weekly",
                min(await self._count_xp(("concept_mastered",), w0, w1), 1),
                1,
                WEEKLY_MISSION_XP,
                w1,
            ),
            Mission(
                "recalls",
                "weekly",
                min(await self._count_xp(("review",), w0, w1), 20),
                20,
                WEEKLY_MISSION_XP,
                w1,
            ),
        ]

    # ── Marks ────────────────────────────────────────────────────────────

    async def _first(self, kinds: tuple[str, ...], nth: int = 1) -> datetime | None:
        """When the nth event of these kinds happened, if it has."""
        found: datetime | None = await self.db.scalar(
            select(XpEvent.occurred_at)
            .where(XpEvent.owner_id == self.owner_id, XpEvent.kind.in_(kinds))
            .order_by(XpEvent.occurred_at)
            .offset(nth - 1)
            .limit(1)
        )
        return found

    async def _earned_marks(self) -> dict[str, datetime]:
        earned: dict[str, datetime] = {}
        first_turn = await self.db.scalar(
            select(func.min(TeachingTurn.created_at)).where(
                TeachingTurn.owner_id == self.owner_id,
                TeachingTurn.role == TurnRole.LEARNER,
            )
        )
        candidates: dict[str, datetime | None] = {
            "first_lesson": first_turn,
            "first_mastered": await self._first(("concept_mastered",)),
            "ten_mastered": await self._first(("concept_mastered",), 10),
            "first_checkpoint": await self._first(("checkpoint",)),
            "hundred_recalls": await self._first(("review",), 100),
            "week_streak": await self._streak_reached(7),
            "path_complete": await self.db.scalar(
                select(func.min(LearningJourney.updated_at)).where(
                    LearningJourney.owner_id == self.owner_id,
                    LearningJourney.status == JourneyStatus.DONE.value,
                )
            ),
        }
        for mark_id, at in candidates.items():
            if at is not None:
                earned[mark_id] = at
        return earned

    async def _streak_reached(self, length: int) -> datetime | None:
        """The end of the first run of `length` consecutive active days."""
        day = func.date(func.timezone("UTC", XpEvent.occurred_at))
        days = sorted(
            {
                row[0]
                for row in await self.db.execute(
                    select(day).where(
                        XpEvent.owner_id == self.owner_id,
                        XpEvent.kind.in_(LEARNING_KINDS),
                    )
                )
            }
        )
        run = 0
        previous: date | None = None
        for current in days:
            run = run + 1 if previous and current - previous == timedelta(days=1) else 1
            previous = current
            if run >= length:
                return datetime(
                    current.year, current.month, current.day, 23, 59, tzinfo=UTC
                )
        return None

    # ── Reading ──────────────────────────────────────────────────────────

    async def summary(self, *, now: datetime | None = None) -> Summary:
        now = now or datetime.now(UTC)
        total = int(
            await self.db.scalar(
                select(func.coalesce(func.sum(XpEvent.xp), 0)).where(
                    XpEvent.owner_id == self.owner_id
                )
            )
            or 0
        )
        d0, d1 = self._day_window(now)
        today = int(
            await self.db.scalar(
                select(func.coalesce(func.sum(XpEvent.xp), 0)).where(
                    XpEvent.owner_id == self.owner_id,
                    XpEvent.occurred_at >= d0,
                    XpEvent.occurred_at < d1,
                )
            )
            or 0
        )
        level = level_for(total)
        marks_at = {
            row.source_id: row.occurred_at
            for row in await self.db.execute(
                select(XpEvent.source_id, XpEvent.occurred_at).where(
                    XpEvent.owner_id == self.owner_id, XpEvent.kind == "mark"
                )
            )
        }
        return Summary(
            level=level,
            stage=stage_for(level),
            xp_total=total,
            level_floor=xp_for_level(level),
            next_level_at=xp_for_level(level + 1),
            xp_today=today,
            missions=await self.missions(now=now),
            marks=[Mark(m, m in marks_at, marks_at.get(m)) for m in MARKS],
        )
