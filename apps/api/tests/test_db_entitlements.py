"""EntitlementsService: what a plan allows this month, and what's already spent.

Migration 0013 seeds all four plans unconditionally (`plan` is `plan_configs`'
primary key, one row per plan, always present), so tests work against the
already-seeded rows the same way `test_db_pricing.py` works against 0012's --
inserting a fresh row under an already-used plan primary key would just
collide with the seed data.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import AIUsage, ModelTier, Plan, PlanConfig, User
from noema.services.entitlements import (
    TOKENS_PER_UNIT,
    EntitlementsService,
    current_period_start,
)
from noema.services.pricing import PricingService

pytestmark = pytest.mark.asyncio


def _usage(
    *,
    owner_id: uuid.UUID,
    prompt_tokens: int,
    completion_tokens: int = 0,
    created_at: datetime | None = None,
) -> AIUsage:
    return AIUsage(
        owner_id=owner_id,
        provider="anthropic",
        model="claude-sonnet-5",
        task="tutor_chat",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        created_at=created_at or datetime.now(UTC),
    )


async def test_a_fresh_user_is_allowed_with_zero_usage(
    db: AsyncSession, user: User
) -> None:
    service = EntitlementsService(db, user)

    check = await service.check_ai_usage()

    assert check.allowed
    assert not check.warn
    assert check.used_units == 0
    free = await db.get(PlanConfig, Plan.FREE)
    assert free is not None
    assert check.limit_units == free.monthly_ai_units


async def test_used_units_is_tokens_floor_divided_by_the_unit_size(
    db: AsyncSession, user: User
) -> None:
    db.add(_usage(owner_id=user.id, prompt_tokens=TOKENS_PER_UNIT * 3 + 999))
    await db.flush()

    check = await EntitlementsService(db, user).check_ai_usage()

    assert check.used_units == 3


async def test_usage_is_blocked_once_the_plan_limit_is_reached(
    db: AsyncSession, user: User
) -> None:
    free = await db.get(PlanConfig, Plan.FREE)
    assert free is not None
    db.add(
        _usage(owner_id=user.id, prompt_tokens=free.monthly_ai_units * TOKENS_PER_UNIT)
    )
    await db.flush()

    check = await EntitlementsService(db, user).check_ai_usage()

    assert not check.allowed
    assert check.remaining_units == 0


async def test_usage_just_under_the_limit_is_allowed(
    db: AsyncSession, user: User
) -> None:
    free = await db.get(PlanConfig, Plan.FREE)
    assert free is not None
    db.add(
        _usage(
            owner_id=user.id,
            prompt_tokens=(free.monthly_ai_units - 1) * TOKENS_PER_UNIT,
        )
    )
    await db.flush()

    check = await EntitlementsService(db, user).check_ai_usage()

    assert check.allowed
    assert check.remaining_units == 1


async def test_warns_once_ten_percent_or_less_remains(
    db: AsyncSession, user: User
) -> None:
    user.plan = Plan.STUDENT
    await db.flush()
    student = await db.get(PlanConfig, Plan.STUDENT)
    assert student is not None
    ninety_percent = round(student.monthly_ai_units * 0.9)
    db.add(_usage(owner_id=user.id, prompt_tokens=ninety_percent * TOKENS_PER_UNIT))
    await db.flush()

    check = await EntitlementsService(db, user).check_ai_usage()

    assert check.allowed
    assert check.warn


async def test_does_not_warn_with_comfortable_headroom(
    db: AsyncSession, user: User
) -> None:
    db.add(_usage(owner_id=user.id, prompt_tokens=5 * TOKENS_PER_UNIT))
    await db.flush()

    check = await EntitlementsService(db, user).check_ai_usage()

    assert check.allowed
    assert not check.warn


async def test_only_the_current_calendar_month_counts(
    db: AsyncSession, user: User
) -> None:
    free = await db.get(PlanConfig, Plan.FREE)
    assert free is not None
    last_month = current_period_start() - timedelta(days=1)
    # Enough tokens to blow the whole monthly limit, but dated before this
    # period started -- must not count against it.
    db.add(
        _usage(
            owner_id=user.id,
            prompt_tokens=free.monthly_ai_units * TOKENS_PER_UNIT * 2,
            created_at=last_month,
        )
    )
    await db.flush()

    check = await EntitlementsService(db, user).check_ai_usage()

    assert check.allowed
    assert check.used_units == 0


async def test_one_users_usage_never_counts_against_another(
    db: AsyncSession, user: User, other_user: User
) -> None:
    db.add(_usage(owner_id=other_user.id, prompt_tokens=50 * TOKENS_PER_UNIT))
    await db.flush()

    check = await EntitlementsService(db, user).check_ai_usage()

    assert check.used_units == 0


#: Must match migration 0014's own documented assumption exactly -- an
#: approximate, explicitly-labelled exchange rate, not a live-fetched one.
#: ``cost_cents`` returns USD cents; ``PlanConfig.monthly_price_cents`` is
#: BRL cents, so the two are not directly comparable without this.
_USD_TO_BRL = 5.20


async def test_a_paid_plan_maxed_out_every_month_still_holds_a_real_margin(
    db: AsyncSession,
) -> None:
    """Migration 0014's whole reason to exist: a plan's monthly_ai_units must
    stay cheap enough, against real per-tier pricing, that even a subscriber
    who spends every unit every month still leaves real margin -- not a
    number a human eyeballed once and never re-checked. A careless future
    edit to either side (looser unit limits, or pricier tiers) that breaks
    this promise should fail CI, not wait to be noticed on a real invoice.

    Blended per-unit cost, worst case, mirrors 0014's own migration comment
    exactly: 80% input / 20% output tokens per call, weighted 10% economy /
    80% standard / 10% premium across tiers -- not a fresh assumption here.
    """
    pricing = PricingService(db)
    tier_share = {
        ModelTier.ECONOMY: 0.10,
        ModelTier.STANDARD: 0.80,
        ModelTier.PREMIUM: 0.10,
    }
    blended_cost_cents_per_unit = 0.0
    for tier, share in tier_share.items():
        tier_config = await pricing.tier_config(tier)
        assert tier_config is not None, f"{tier} must have a seeded price row"
        cost_cents = await pricing.cost_cents(
            provider=tier_config.provider,
            model=tier_config.model,
            prompt_tokens=800,  # 1,000 combined tokens (1 unit), 80% input
            completion_tokens=200,  # 20% output
        )
        blended_cost_cents_per_unit += share * cost_cents

    for plan in (Plan.STUDENT, Plan.PRO, Plan.MAX):
        plan_config = await db.get(PlanConfig, plan)
        assert plan_config is not None
        assert plan_config.monthly_price_cents > 0, f"{plan} must have a real price"

        worst_case_ai_cost_usd_cents = (
            blended_cost_cents_per_unit * plan_config.monthly_ai_units
        )
        worst_case_ai_cost_brl_cents = worst_case_ai_cost_usd_cents * _USD_TO_BRL
        ai_cost_fraction = worst_case_ai_cost_brl_cents / plan_config.monthly_price_cents

        # 30%, not 20.9%'s exact figure from the migration comment: real
        # headroom for the comment's own rounding (it deliberately rounds the
        # per-unit cost UP to $0.004), not a test pinned so tightly it flakes
        # on the next cent of legitimate rounding.
        assert ai_cost_fraction < 0.30, (
            f"{plan}: AI cost alone is {ai_cost_fraction:.1%} of the monthly "
            f"price at 100% utilization -- too thin a margin once payment "
            f"fees and infra are subtracted"
        )


async def test_free_plans_worst_case_cost_is_bounded(db: AsyncSession) -> None:
    """Free has no price to compare against -- what matters is that the
    platform's per-free-account cost exposure stays small and deliberate,
    not that it clears some margin percentage of a $0 price."""
    pricing = PricingService(db)
    free = await db.get(PlanConfig, Plan.FREE)
    assert free is not None
    standard = await pricing.tier_config(ModelTier.STANDARD)
    assert standard is not None

    # Worst case: every unit spent on the most expensive plausible everyday
    # tier (standard, not premium -- a free account never reaches "deepen").
    total_tokens = free.monthly_ai_units * TOKENS_PER_UNIT
    worst_case_cost_cents = await pricing.cost_cents(
        provider=standard.provider,
        model=standard.model,
        prompt_tokens=round(total_tokens * 0.8),
        completion_tokens=round(total_tokens * 0.2),
    )

    # $1.00 (100 cents) a month per free account -- a real, deliberate cost
    # ceiling for customer acquisition, not an accident.
    assert worst_case_cost_cents < 100.0


async def test_falls_back_to_free_plan_if_the_users_plan_has_no_config_row(
    db: AsyncSession, user: User
) -> None:
    # Real, if currently unreachable, failure mode: a plan added later
    # without its own config row must not read as unlimited.
    user.plan = Plan.PRO
    pro = await db.get(PlanConfig, Plan.PRO)
    assert pro is not None
    await db.delete(pro)
    await db.flush()
    free = await db.get(PlanConfig, Plan.FREE)
    assert free is not None

    check = await EntitlementsService(db, user).check_ai_usage()

    assert check.limit_units == free.monthly_ai_units
