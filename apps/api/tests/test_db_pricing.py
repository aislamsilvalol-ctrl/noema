"""PricingService: what a tier points at, and what a call actually cost.

No test existed for this before it existed — the module itself is new (Phase 1 of
the SaaS pivot). The one behavior worth pinning hardest: an unconfigured (or
zero-priced) model must compute to 0.0, not raise and not silently guess.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import ModelTier, ModelTierConfig
from noema.services.pricing import PricingService

pytestmark = pytest.mark.asyncio


async def test_cost_cents_is_zero_for_an_unconfigured_model(db: AsyncSession) -> None:
    service = PricingService(db)

    cost = await service.cost_cents(
        provider="anthropic",
        model="does-not-exist",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
    )

    assert cost == 0.0


async def test_cost_cents_is_zero_for_a_configured_but_unpriced_tier(
    db: AsyncSession,
) -> None:
    db.add(
        ModelTierConfig(
            tier=ModelTier.ECONOMY, provider="anthropic", model="claude-haiku-test"
        )
    )
    await db.flush()
    service = PricingService(db)

    cost = await service.cost_cents(
        provider="anthropic",
        model="claude-haiku-test",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
    )

    assert cost == 0.0


async def test_cost_cents_computes_input_and_output_separately(
    db: AsyncSession,
) -> None:
    db.add(
        ModelTierConfig(
            tier=ModelTier.PREMIUM,
            provider="anthropic",
            model="claude-opus-test",
            input_cost_per_million_usd=4.0,
            output_cost_per_million_usd=20.0,
        )
    )
    await db.flush()
    service = PricingService(db)

    cost = await service.cost_cents(
        provider="anthropic",
        model="claude-opus-test",
        prompt_tokens=500_000,
        completion_tokens=250_000,
    )

    # (500_000/1e6)*$4.00 + (250_000/1e6)*$20.00 = $2.00 + $5.00 = $7.00 = 700 cents.
    assert cost == pytest.approx(700.0)


async def test_cost_cents_is_scoped_by_the_exact_provider_and_model_pair(
    db: AsyncSession,
) -> None:
    db.add(
        ModelTierConfig(
            tier=ModelTier.STANDARD,
            provider="anthropic",
            model="claude-sonnet-test",
            input_cost_per_million_usd=3.0,
            output_cost_per_million_usd=15.0,
        )
    )
    await db.flush()
    service = PricingService(db)

    # Same model string, different provider -- must not match the row above.
    cost = await service.cost_cents(
        provider="openai",
        model="claude-sonnet-test",
        prompt_tokens=1_000_000,
        completion_tokens=0,
    )

    assert cost == 0.0


async def test_tier_config_looks_up_by_tier(db: AsyncSession) -> None:
    db.add(
        ModelTierConfig(tier=ModelTier.STANDARD, provider="anthropic", model="claude-5")
    )
    await db.flush()
    service = PricingService(db)

    config = await service.tier_config(ModelTier.STANDARD)

    assert config is not None
    assert config.provider == "anthropic"
    assert config.model == "claude-5"


async def test_tier_config_is_none_for_an_unseeded_tier(db: AsyncSession) -> None:
    service = PricingService(db)

    assert await service.tier_config(ModelTier.ECONOMY) is None


async def test_all_tiers_returns_every_configured_row(db: AsyncSession) -> None:
    db.add_all(
        [
            ModelTierConfig(tier=ModelTier.ECONOMY, provider="anthropic", model="a"),
            ModelTierConfig(tier=ModelTier.PREMIUM, provider="anthropic", model="c"),
        ]
    )
    await db.flush()
    service = PricingService(db)

    tiers = await service.all_tiers()

    assert [t.tier for t in tiers] == [ModelTier.ECONOMY, ModelTier.PREMIUM]
