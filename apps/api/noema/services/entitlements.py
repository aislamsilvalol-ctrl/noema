"""Plan limits, decoupled from any payment provider.

Feature code asks ``EntitlementsService(db, user).check_ai_usage()`` -- never a
plan name, never a Stripe price id. Only a verified billing webhook (or an
admin) sets ``User.plan``.

A learner never sees what is metered. They see "aulas completas" and "modo
padrão" (migration 0041). Inside, usage is counted in credits of real cost:
1 credit = US$0.001 of AI spend as ``ai_usage`` records it, priced from
``model_prices``. A limit in credits holds whatever the model mix or the price
list does, which a limit in tokens never did (a token of Opus costs 40 times
a token of Haiku 5.5).

The month runs in two steps:

- up to ``full_credits``, lessons run on the full routing;
- past it, they continue in standard mode (the economy tier) instead of
  stopping, up to ``hard_credits``. Past that the tutor waits for next month.

``daily_turns`` and ``weekly_lessons`` bound the pace on top.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import Float, Select, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from noema.db.models import (
    AIUsage,
    JourneyStatus,
    LearningJourney,
    Plan,
    PlanConfig,
    Source,
    TeachingTurn,
    TurnRole,
    User,
)
from noema.services.pricing import MICRO_CENTS_PER_CENT

#: 1 credit = US$0.001 = 0.1 cent.
MICRO_CENTS_PER_CREDIT = MICRO_CENTS_PER_CENT // 10

#: About what one lesson of ten exchanges costs on the full routing, in
#: credits (Sonnet 5.5 with the cache, `docs/pricing/PRICING_AUDIT.md`). Only
#: used to say "about N full lessons"; nothing is limited by it.
CREDITS_PER_FULL_LESSON = 74

#: Warn once 10% or less of the full lessons remain -- seen coming, not hit
#: with no notice, per the product's "no aggressive paywall" requirement.
WARN_FRACTION = 0.1


class Mode(StrEnum):
    FULL = "full"
    STANDARD = "standard"


class LimitReason(StrEnum):
    MONTHLY = "monthly"
    DAILY = "daily"
    WEEKLY = "weekly"
    DOCUMENTS = "documents"
    JOURNEYS = "journeys"


@dataclass(frozen=True, slots=True)
class EntitlementCheck:
    allowed: bool
    warn: bool
    plan: Plan
    mode: Mode
    used_credits: int
    full_credits: int
    hard_credits: int
    reason: LimitReason | None = None
    #: When the limit that blocked (or the full lessons) come back.
    resets_at: datetime | None = None

    @property
    def standard(self) -> bool:
        return self.mode is Mode.STANDARD

    # The names clients read before credits existed.
    @property
    def used_units(self) -> int:
        return self.used_credits

    @property
    def limit_units(self) -> int:
        return self.hard_credits

    @property
    def remaining_units(self) -> int:
        return max(self.hard_credits - self.used_credits, 0)

    def public(self) -> dict[str, object]:
        """What the client is told: modes, reasons and dates, not credits."""
        return {
            "plan": self.plan.value,
            "mode": self.mode.value,
            "reason": self.reason.value if self.reason else None,
            "resets_at": self.resets_at.isoformat() if self.resets_at else None,
            "full_lessons_left": max(self.full_credits - self.used_credits, 0)
            // CREDITS_PER_FULL_LESSON,
            # Kept for clients that read them.
            "used_units": self.used_credits,
            "limit_units": self.hard_credits,
        }


def current_period_start(now: datetime | None = None) -> datetime:
    """The first instant of the current calendar month, UTC.

    Calendar-month, not a rolling 30-day window: a subscription bills in
    calendar months, and a usage limit that resets on a different schedule
    than the bill would confuse the moment both exist.
    """
    now = now or datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_period_start(now: datetime | None = None) -> datetime:
    start = current_period_start(now)
    return (start + timedelta(days=32)).replace(day=1)


def credits_sum() -> ColumnElement[Any]:
    """The credits a group of `ai_usage` rows cost: integer micro-cents when
    written, else the legacy float of cents."""
    micro = func.coalesce(
        cast(AIUsage.cost_micro_cents, Float),
        AIUsage.cost_cents * float(MICRO_CENTS_PER_CENT),
    )
    return func.coalesce(func.sum(micro), 0.0) / MICRO_CENTS_PER_CREDIT


def credits_used_since(owner_id: uuid.UUID, since: datetime) -> Select[Any]:
    """A scalar select of the credits `owner_id` spent since `since`."""
    return select(credits_sum()).where(
        AIUsage.owner_id == owner_id, AIUsage.created_at >= since
    )


class EntitlementsService:
    def __init__(self, session: AsyncSession, user: User) -> None:
        self.db = session
        self.user = user

    async def plan_config(self) -> PlanConfig:
        config = await self.db.get(PlanConfig, self.user.plan)
        if config is not None:
            return config
        # A plan added later without a matching config row: Free's limit is
        # the safe direction to be wrong in; "unlimited" is not.
        free = await self.db.get(PlanConfig, Plan.FREE)
        assert free is not None, "Plan.FREE must always have a config row"
        return free

    async def credits_this_period(self) -> int:
        used = await self.db.scalar(
            credits_used_since(self.user.id, current_period_start())
        )
        return int(used or 0)

    async def check_ai_usage(
        self, *, session_id: uuid.UUID | None = None
    ) -> EntitlementCheck:
        """Whether the learner may talk to the tutor now, and in which mode.

        `session_id` is the lesson the message continues: a lesson already
        under way this week never counts against the weekly limit again.
        """
        config = await self.plan_config()
        used = await self.credits_this_period()
        now = datetime.now(UTC)

        def check(
            allowed: bool,
            mode: Mode,
            *,
            reason: LimitReason | None = None,
            resets_at: datetime | None = None,
            warn: bool = False,
        ) -> EntitlementCheck:
            return EntitlementCheck(
                allowed=allowed,
                warn=warn,
                plan=config.plan,
                mode=mode,
                used_credits=used,
                full_credits=config.full_credits,
                hard_credits=config.hard_credits,
                reason=reason,
                resets_at=resets_at,
            )

        mode = Mode.FULL if used < config.full_credits else Mode.STANDARD
        if used >= config.hard_credits:
            return check(
                False, mode, reason=LimitReason.MONTHLY, resets_at=next_period_start(now)
            )

        if config.daily_turns is not None:
            since = now - timedelta(days=1)
            turns = await self._learner_turns(since)
            if len(turns) >= config.daily_turns:
                return check(
                    False,
                    mode,
                    reason=LimitReason.DAILY,
                    resets_at=min(turns) + timedelta(days=1),
                )

        if config.weekly_lessons is not None:
            since = now - timedelta(days=7)
            lessons = await self._lessons_since(since)
            if session_id not in lessons and len(lessons) >= config.weekly_lessons:
                return check(
                    False,
                    mode,
                    reason=LimitReason.WEEKLY,
                    resets_at=min(lessons.values()) + timedelta(days=7),
                )

        left = config.full_credits - used
        warn = mode is Mode.FULL and left <= max(
            round(config.full_credits * WARN_FRACTION), CREDITS_PER_FULL_LESSON
        )
        resets = next_period_start(now) if mode is Mode.STANDARD or warn else None
        return check(True, mode, warn=warn, resets_at=resets)

    async def check_documents(self) -> EntitlementCheck | None:
        """None when another document may be added this month; else why not."""
        config = await self.plan_config()
        if config.monthly_documents is None:
            return None
        count = await self.db.scalar(
            select(func.count(Source.id)).where(
                Source.owner_id == self.user.id,
                Source.created_at >= current_period_start(),
            )
        )
        if int(count or 0) < config.monthly_documents:
            return None
        used = await self.credits_this_period()
        return EntitlementCheck(
            allowed=False,
            warn=False,
            plan=config.plan,
            mode=Mode.FULL if used < config.full_credits else Mode.STANDARD,
            used_credits=used,
            full_credits=config.full_credits,
            hard_credits=config.hard_credits,
            reason=LimitReason.DOCUMENTS,
            resets_at=next_period_start(),
        )

    async def may_start_journey(self) -> bool:
        config = await self.plan_config()
        if config.max_journeys is None:
            return True
        count = await self.db.scalar(
            select(func.count(LearningJourney.id)).where(
                LearningJourney.owner_id == self.user.id,
                LearningJourney.status == JourneyStatus.ACTIVE.value,
            )
        )
        return int(count or 0) < config.max_journeys

    async def _learner_turns(self, since: datetime) -> list[datetime]:
        rows = await self.db.scalars(
            select(TeachingTurn.created_at).where(
                TeachingTurn.owner_id == self.user.id,
                TeachingTurn.role == TurnRole.LEARNER,
                TeachingTurn.created_at >= since,
            )
        )
        return list(rows)

    async def _lessons_since(self, since: datetime) -> dict[uuid.UUID, datetime]:
        """Lessons the learner spoke in since `since`, each with its first
        message in that window."""
        rows = await self.db.execute(
            select(TeachingTurn.session_id, func.min(TeachingTurn.created_at))
            .where(
                TeachingTurn.owner_id == self.user.id,
                TeachingTurn.role == TurnRole.LEARNER,
                TeachingTurn.created_at >= since,
            )
            .group_by(TeachingTurn.session_id)
        )
        return {row[0]: row[1] for row in rows.all()}


__all__ = [
    "CREDITS_PER_FULL_LESSON",
    "EntitlementCheck",
    "EntitlementsService",
    "LimitReason",
    "Mode",
    "credits_sum",
    "credits_used_since",
    "current_period_start",
    "next_period_start",
]
