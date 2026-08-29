"""PricingService: what a tier points at, and what a call actually cost.

No test existed for this before it existed — the module itself is new (Phase 1 of
the SaaS pivot). Migration 0012 seeds all three tiers unconditionally (``tier`` is
the table's primary key, one row per tier, always present after that migration
runs), so every test here works against the already-seeded rows rather than
inserting fresh ones -- there is no "unseeded tier" state in any real deployment
to test against, and inserting a second row under an already-used tier would just
collide with the seed data's own primary key.
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


async def test_cost_cents_is_zero_for_a_freshly_seeded_tier(db: AsyncSession) -> None:
    """Migration 0012 seeds every tier's pricing at 0.0 on purpose -- confirms the
    seed data itself, not just the calculation, reads as "not priced yet."""
    economy = await db.get(ModelTierConfig, ModelTier.ECONOMY)
    assert economy is not None
    service = PricingService(db)

    cost = await service.cost_cents(
        provider=economy.provider,
        model=economy.model,
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
    )

    assert cost == 0.0


async def test_cost_cents_computes_input_and_output_separately(
    db: AsyncSession,
) -> None:
    premium = await db.get(ModelTierConfig, ModelTier.PREMIUM)
    assert premium is not None
    premium.input_cost_per_million_usd = 4.0
    premium.output_cost_per_million_usd = 20.0
    await db.flush()
    service = PricingService(db)

    cost = await service.cost_cents(
        provider=premium.provider,
        model=premium.model,
        prompt_tokens=500_000,
        completion_tokens=250_000,
    )

    # (500_000/1e6)*$4.00 + (250_000/1e6)*$20.00 = $2.00 + $5.00 = $7.00 = 700 cents.
    assert cost == pytest.approx(700.0)


async def test_cost_cents_is_scoped_by_the_exact_provider_and_model_pair(
    db: AsyncSession,
) -> None:
    standard = await db.get(ModelTierConfig, ModelTier.STANDARD)
    assert standard is not None
    standard.input_cost_per_million_usd = 3.0
    standard.output_cost_per_million_usd = 15.0
    await db.flush()
    service = PricingService(db)

    # Same model string, a provider that doesn't hold this pricing -- must not match.
    cost = await service.cost_cents(
        provider="openai",
        model=standard.model,
        prompt_tokens=1_000_000,
        completion_tokens=0,
    )

    assert cost == 0.0


async def test_tier_config_looks_up_the_seeded_standard_tier(db: AsyncSession) -> None:
    service = PricingService(db)

    config = await service.tier_config(ModelTier.STANDARD)

    assert config is not None
    assert config.provider == "anthropic"
    assert config.model == "claude-sonnet-5"


async def test_all_tiers_returns_exactly_the_three_seeded_rows(
    db: AsyncSession,
) -> None:
    service = PricingService(db)

    tiers = await service.all_tiers()

    assert [t.tier for t in tiers] == [
        ModelTier.ECONOMY,
        ModelTier.STANDARD,
        ModelTier.PREMIUM,
    ]
    assert {t.provider for t in tiers} == {"anthropic"}
