"""EconomicsSimulator: pure math, deterministic, no DB writes -- but it reads
real tier pricing from ModelTierConfig, so it still needs a DB session against
the already-seeded rows (see test_db_pricing.py's own note on why a fresh
insert under an already-used tier primary key would collide).
"""

from __future__ import annotations

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import ModelTier, ModelTierConfig
from noema.services.economics import EconomicsSimulator, SimulatorInputs

pytestmark = pytest.mark.asyncio


async def _price_tier(
    db: AsyncSession,
    tier: ModelTier,
    *,
    input_per_million: float,
    output_per_million: float,
) -> None:
    await db.execute(
        update(ModelTierConfig)
        .where(ModelTierConfig.tier == tier)
        .values(
            input_cost_per_million_usd=input_per_million,
            output_cost_per_million_usd=output_per_million,
        )
    )
    await db.flush()


async def test_zero_subscribers_is_zero_everything_not_a_crash(db: AsyncSession) -> None:
    result = await EconomicsSimulator(db).simulate(
        SimulatorInputs(
            subscribers=0,
            messages_per_day=10,
            avg_input_tokens=500,
            avg_output_tokens=500,
            tier_mix={ModelTier.STANDARD: 1.0},
            active_days_per_month=20,
            plan_price_cents=5990,
        )
    )

    assert result.gross_revenue_cents == 0
    assert result.ai_cost_total_cents == 0
    assert result.gross_margin_percent == 0.0  # not a ZeroDivisionError


async def test_known_inputs_produce_known_ai_cost(db: AsyncSession) -> None:
    await _price_tier(
        db, ModelTier.ECONOMY, input_per_million=1.0, output_per_million=2.0
    )

    result = await EconomicsSimulator(db).simulate(
        SimulatorInputs(
            subscribers=1,
            messages_per_day=1,
            avg_input_tokens=1_000_000,
            avg_output_tokens=1_000_000,
            tier_mix={ModelTier.ECONOMY: 1.0},
            active_days_per_month=1,
            plan_price_cents=0,
            payment_fee_percent=0,
            payment_fee_fixed_cents=0,
            billing_fee_percent=0,
            tax_percent=0,
        )
    )

    # 1M input tokens @ $1/M + 1M output tokens @ $2/M = $3.00 = 300 cents,
    # for exactly one message from exactly one subscriber.
    assert result.ai_cost_per_user_cents == pytest.approx(300.0)
    assert result.ai_cost_total_cents == pytest.approx(300.0)


async def test_tier_mix_blends_cost_proportionally(db: AsyncSession) -> None:
    await _price_tier(
        db, ModelTier.ECONOMY, input_per_million=1.0, output_per_million=1.0
    )
    await _price_tier(
        db, ModelTier.PREMIUM, input_per_million=10.0, output_per_million=10.0
    )

    result = await EconomicsSimulator(db).simulate(
        SimulatorInputs(
            subscribers=1,
            messages_per_day=1,
            avg_input_tokens=1_000_000,
            avg_output_tokens=0,
            tier_mix={ModelTier.ECONOMY: 0.8, ModelTier.PREMIUM: 0.2},
            active_days_per_month=1,
            plan_price_cents=0,
        )
    )

    # 0.8 * $1 + 0.2 * $10 = $2.80 = 280 cents per message.
    assert result.ai_cost_per_user_cents == pytest.approx(280.0)


async def test_fees_and_margin_computed_from_real_revenue(db: AsyncSession) -> None:
    await _price_tier(
        db, ModelTier.STANDARD, input_per_million=0.0, output_per_million=0.0
    )

    result = await EconomicsSimulator(db).simulate(
        SimulatorInputs(
            subscribers=100,
            messages_per_day=0,
            avg_input_tokens=0,
            avg_output_tokens=0,
            tier_mix={ModelTier.STANDARD: 1.0},
            active_days_per_month=30,
            plan_price_cents=5000,
            payment_fee_percent=4.0,
            payment_fee_fixed_cents=39.0,
            billing_fee_percent=1.0,
            tax_percent=0,
        )
    )

    # Zero AI cost (priced at $0/M and zero messages), so margin is pure fees.
    assert result.gross_revenue_cents == pytest.approx(500_000.0)
    # payment: 100 * (5000*0.04 + 39) = 100 * 239 = 23_900
    # billing: 500_000 * 0.01 = 5_000
    assert result.payment_fees_cents == pytest.approx(28_900.0)
    assert result.net_revenue_cents == pytest.approx(500_000 - 28_900)
    assert result.estimated_mrr_cents == pytest.approx(500_000.0)


async def test_an_unpriced_tier_contributes_zero_not_an_error(db: AsyncSession) -> None:
    # Every tier is seeded at $0.0 by migration 0012 until an operator sets
    # real prices -- the simulator must not crash or fabricate a number.
    result = await EconomicsSimulator(db).simulate(
        SimulatorInputs(
            subscribers=10,
            messages_per_day=5,
            avg_input_tokens=1000,
            avg_output_tokens=1000,
            tier_mix={ModelTier.PREMIUM: 1.0},
            active_days_per_month=30,
            plan_price_cents=9990,
        )
    )

    assert result.ai_cost_total_cents == 0.0
