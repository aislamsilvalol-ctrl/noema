"""EntitlementsService: what a plan allows this month, and what's already spent.

Migration 0041 seeds Free / Plus / Pro (and keeps Student / Max, unsold). Tests
work against the seeded rows. Usage is counted in credits of real cost (1 =
US$0.001), from `ai_usage.cost_micro_cents`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import (
    AIUsage,
    JourneyStatus,
    LearningJourney,
    Plan,
    PlanConfig,
    TeachingSession,
    TeachingTurn,
    TurnRole,
    User,
)
from noema.services.entitlements import (
    CREDITS_PER_FULL_LESSON,
    EntitlementsService,
    LimitReason,
    Mode,
    current_period_start,
    next_period_start,
)

pytestmark = pytest.mark.asyncio

#: 1 credit = 100,000 micro-cents.
CREDIT = 100_000


def _spent(
    owner_id: uuid.UUID, amount: int, *, created_at: datetime | None = None
) -> AIUsage:
    return AIUsage(
        owner_id=owner_id,
        provider="anthropic",
        model="claude-sonnet-5-5",
        task="tutor_chat",
        prompt_tokens=1_000,
        completion_tokens=100,
        cost_cents=amount / 10,
        cost_micro_cents=amount * CREDIT,
        created_at=created_at or datetime.now(UTC),
    )


async def _config(db: AsyncSession, plan: Plan) -> PlanConfig:
    config = await db.get(PlanConfig, plan)
    assert config is not None
    return config


async def _turns(
    db: AsyncSession, user: User, count: int, *, session: TeachingSession | None = None
) -> TeachingSession:
    session = session or TeachingSession(owner_id=user.id, learning_goal="x")
    db.add(session)
    await db.flush()
    for _ in range(count):
        db.add(
            TeachingTurn(
                owner_id=user.id,
                session_id=session.id,
                role=TurnRole.LEARNER,
                content="q",
            )
        )
    await db.flush()
    return session


async def test_a_fresh_user_is_in_full_mode(db: AsyncSession, user: User) -> None:
    check = await EntitlementsService(db, user).check_ai_usage()

    assert check.allowed and not check.warn
    assert check.mode is Mode.FULL
    assert check.used_credits == 0
    assert check.plan is Plan.FREE


async def test_past_the_full_lessons_the_tutor_goes_on_in_standard_mode(
    db: AsyncSession, user: User
) -> None:
    free = await _config(db, Plan.FREE)
    db.add(_spent(user.id, free.full_credits))
    await db.flush()

    check = await EntitlementsService(db, user).check_ai_usage()

    assert check.allowed
    assert check.mode is Mode.STANDARD
    assert check.resets_at == next_period_start()


async def test_the_hard_ceiling_blocks_until_next_month(
    db: AsyncSession, user: User
) -> None:
    free = await _config(db, Plan.FREE)
    db.add(_spent(user.id, free.hard_credits))
    await db.flush()

    check = await EntitlementsService(db, user).check_ai_usage()

    assert not check.allowed
    assert check.reason is LimitReason.MONTHLY
    assert check.resets_at == next_period_start()
    assert check.public()["reason"] == "monthly"


async def test_a_warning_comes_before_the_full_lessons_run_out(
    db: AsyncSession, user: User
) -> None:
    free = await _config(db, Plan.FREE)
    db.add(_spent(user.id, free.full_credits - CREDITS_PER_FULL_LESSON // 2))
    await db.flush()

    check = await EntitlementsService(db, user).check_ai_usage()

    assert check.allowed and check.warn and check.mode is Mode.FULL


async def test_last_months_spend_does_not_count(db: AsyncSession, user: User) -> None:
    free = await _config(db, Plan.FREE)
    db.add(
        _spent(
            user.id,
            free.hard_credits * 2,
            created_at=current_period_start() - timedelta(seconds=1),
        )
    )
    await db.flush()

    check = await EntitlementsService(db, user).check_ai_usage()

    assert check.allowed and check.used_credits == 0


async def test_another_learners_spend_does_not_count(
    db: AsyncSession, user: User, other_user: User
) -> None:
    db.add(_spent(other_user.id, 10_000))
    await db.flush()

    check = await EntitlementsService(db, user).check_ai_usage()

    assert check.used_credits == 0


async def test_a_paid_plan_has_more_full_lessons(db: AsyncSession, user: User) -> None:
    free = await _config(db, Plan.FREE)
    user.plan = Plan.PLUS
    db.add(_spent(user.id, free.hard_credits))
    await db.flush()

    check = await EntitlementsService(db, user).check_ai_usage()

    assert check.allowed and check.mode is Mode.FULL and check.plan is Plan.PLUS


async def test_the_daily_limit_counts_messages_in_the_last_24_hours(
    db: AsyncSession, user: User
) -> None:
    free = await _config(db, Plan.FREE)
    assert free.daily_turns is not None
    await _turns(db, user, free.daily_turns)

    check = await EntitlementsService(db, user).check_ai_usage()

    assert not check.allowed and check.reason is LimitReason.DAILY
    assert check.resets_at is not None and check.resets_at > datetime.now(UTC)


async def test_free_starts_three_lessons_a_week_and_may_finish_them(
    db: AsyncSession, user: User
) -> None:
    free = await _config(db, Plan.FREE)
    assert free.weekly_lessons == 3
    sessions = [await _turns(db, user, 1) for _ in range(3)]
    service = EntitlementsService(db, user)

    new = await service.check_ai_usage()
    ongoing = await service.check_ai_usage(session_id=sessions[0].id)

    assert not new.allowed and new.reason is LimitReason.WEEKLY
    assert ongoing.allowed


async def test_paid_plans_have_no_weekly_limit(db: AsyncSession, user: User) -> None:
    user.plan = Plan.PLUS
    for _ in range(5):
        await _turns(db, user, 1)

    check = await EntitlementsService(db, user).check_ai_usage()

    assert check.allowed


async def test_free_keeps_one_trail_open(db: AsyncSession, user: User) -> None:
    service = EntitlementsService(db, user)
    assert await service.may_start_journey()

    db.add(
        LearningJourney(
            owner_id=user.id, subject="Química", status=JourneyStatus.ACTIVE.value
        )
    )
    await db.flush()

    assert not await service.may_start_journey()
    user.plan = Plan.PLUS
    assert await service.may_start_journey()


async def test_only_free_plus_and_pro_are_on_sale(db: AsyncSession) -> None:
    rows = await db.scalars(
        select(PlanConfig).where(PlanConfig.active.is_(True)).order_by(PlanConfig.sort)
    )
    plans = [(r.plan, r.monthly_price_cents, r.annual_price_cents) for r in rows]

    assert plans == [
        (Plan.FREE, 0, None),
        (Plan.PLUS, 3490, 34900),
        (Plan.PRO, 6990, 69900),
    ]


#: Planning FX (docs/pricing): R$5,65 per US$.
_USD_TO_BRL = 5.65


async def test_a_paid_plan_spent_to_its_ceiling_does_not_lose_money(
    db: AsyncSession,
) -> None:
    """Migration 0041's promise: every credit of a paid plan spent, every
    month, still costs less than the plan earns after tax (6%), refunds (2%)
    and gateway fees (3.99% + 0.7% + R$0,39). A looser ceiling should fail
    CI, not wait to be noticed on an invoice."""
    for plan in (Plan.PLUS, Plan.PRO):
        config = await _config(db, plan)
        price = config.monthly_price_cents / 100
        net = price * (1 - 0.06 - 0.02 - 0.0399 - 0.007) - 0.39
        ceiling = config.hard_credits / 1000 * _USD_TO_BRL
        assert ceiling < net, f"{plan}: R${ceiling:.2f} of AI against R${net:.2f} net"

    free = await _config(db, Plan.FREE)
    assert free.hard_credits / 1000 * _USD_TO_BRL <= 1.50
