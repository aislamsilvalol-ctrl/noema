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

from noema.db.models import AIUsage, Plan, PlanConfig, User
from noema.services.entitlements import (
    TOKENS_PER_UNIT,
    EntitlementsService,
    current_period_start,
)

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
