"""Plan limits, decoupled from any payment provider.

Feature code asks ``EntitlementsService(db, user).check_ai_usage()`` -- never a
plan name, never a Stripe price id. What eventually *sets* ``User.plan`` is
Phase 8's problem (a webhook writes it once Stripe exists); until then every
account starts and stays on :attr:`Plan.FREE`, the same as every account on
this deployment today, and this module already enforces that plan's real limit.

The user-facing unit is "AI Compute Units," never tokens -- the product's own
requirement is that a student should not need to know what a token is. The
conversion lives in exactly one place (:data:`TOKENS_PER_UNIT`) so a future
pricing rework changes one number, not every call site.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import AIUsage, Plan, PlanConfig, User

#: 1 AI Compute Unit = this many prompt+completion tokens, combined. A round
#: number chosen for readability, not derived from real cost -- pricing
#: (noema/services/pricing.py) is a separate axis, seeded at $0.0 until an
#: operator sets real prices, and a unit's meaning must not depend on that.
TOKENS_PER_UNIT = 1_000

#: Warn once 10% or less of the monthly budget remains (but always warn once at
#: least one unit remains, on a plan too small for 10% to round to anything) --
#: seen coming, not hit with no notice, per the product's "no aggressive
#: paywall" requirement.
WARN_FRACTION = 0.1


@dataclass(frozen=True, slots=True)
class EntitlementCheck:
    allowed: bool
    warn: bool
    used_units: int
    limit_units: int

    @property
    def remaining_units(self) -> int:
        return max(self.limit_units - self.used_units, 0)


def current_period_start(now: datetime | None = None) -> datetime:
    """The first instant of the current calendar month, UTC.

    Calendar-month, not a rolling 30-day window: a subscription bills in
    calendar months, and a usage limit that resets on a different schedule
    than the bill would confuse the moment both exist (Phase 8).
    """
    now = now or datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


class EntitlementsService:
    def __init__(self, session: AsyncSession, user: User) -> None:
        self.db = session
        self.user = user

    async def _plan_config(self) -> PlanConfig:
        config = await self.db.get(PlanConfig, self.user.plan)
        if config is not None:
            return config
        # Unreachable today -- migration 0013 seeds all four plans
        # unconditionally -- but a plan added later without a matching config
        # row is a real future failure mode. Falling back to Free's limit is
        # the safe direction to be wrong in; treating a missing row as
        # "unlimited" is not.
        free = await self.db.get(PlanConfig, Plan.FREE)
        assert free is not None, "Plan.FREE must always have a config row"
        return free

    async def _used_units_this_period(self) -> int:
        total_tokens = await self.db.scalar(
            select(
                func.coalesce(
                    func.sum(AIUsage.prompt_tokens + AIUsage.completion_tokens), 0
                )
            ).where(
                AIUsage.owner_id == self.user.id,
                AIUsage.created_at >= current_period_start(),
            )
        )
        return int(total_tokens or 0) // TOKENS_PER_UNIT

    async def check_ai_usage(self) -> EntitlementCheck:
        """The one gated feature this phase implements for real.

        Named for what it actually checks rather than the spec's fully
        generic ``canUseFeature(user, feature)`` -- that shape is the right
        target once a second real limit (uploads, notebooks, ...) exists to
        dispatch to; a one-branch dispatcher pretending to be generic today
        would be fake generality, not real architecture.
        """
        config = await self._plan_config()
        used = await self._used_units_this_period()
        limit = config.monthly_ai_units
        allowed = used < limit
        warn = allowed and (limit - used) <= max(round(limit * WARN_FRACTION), 1)
        return EntitlementCheck(
            allowed=allowed, warn=warn, used_units=used, limit_units=limit
        )
