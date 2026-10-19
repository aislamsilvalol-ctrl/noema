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

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import ModelPrice, ModelTier, ModelTierConfig
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


async def test_cost_cents_uses_list_prices_for_a_failover_model_without_a_tier(
    db: AsyncSession,
) -> None:
    """OpenAI serving an interleaved or failed-over call has no tier row; its
    known list price is used instead of a silent 0."""
    service = PricingService(db)

    cost = await service.cost_cents(
        provider="openai",
        model="gpt-4.1",
        prompt_tokens=1_000_000,
        completion_tokens=500_000,
        cached_tokens=200_000,
    )

    # 800k fresh * $2.00 + 200k cached * $0.50 + 500k out * $8.00 = $5.70.
    assert cost == pytest.approx(570.0)


async def test_cost_cents_is_nonzero_for_a_seeded_tier(db: AsyncSession) -> None:
    """Migration 0012 seeded every tier's pricing at 0.0 on purpose ("not priced
    yet"); migration 0014 filled in real prices, since an operator has now set
    them. Confirms the seed data itself, not just the calculation, reads as
    genuinely priced -- a regression to an unpriced seed would silently zero
    out every usage-accounting and entitlements number downstream."""
    economy = await db.get(ModelTierConfig, ModelTier.ECONOMY)
    assert economy is not None
    service = PricingService(db)

    cost = await service.cost_cents(
        provider=economy.provider,
        model=economy.model,
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
    )

    assert cost > 0.0


async def test_cost_cents_computes_input_and_output_separately(
    db: AsyncSession,
) -> None:
    """A tier row prices a model the price table does not list."""
    premium = await db.get(ModelTierConfig, ModelTier.PREMIUM)
    assert premium is not None
    premium.model = "claude-custom-unlisted"
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
    standard.model = "claude-custom-unlisted"
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


async def test_cost_cents_prices_a_dated_openai_snapshot(db: AsyncSession) -> None:
    """OpenAI answers as "gpt-4.1-mini-2025-04-14" whatever alias was asked
    for; now that ai_usage records the model that served the call, that name
    must price like the alias (2026-10-07 eval: every row cost $0)."""
    service = PricingService(db)

    dated = await service.cost_cents(
        provider="openai",
        model="gpt-4.1-mini-2025-04-14",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
    )
    alias = await service.cost_cents(
        provider="openai",
        model="gpt-4.1-mini",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
    )

    # $0.40 in + $1.60 out per million.
    assert dated == alias == pytest.approx(200.0)


async def test_the_price_table_wins_over_a_tier_row(db: AsyncSession) -> None:
    """`model_prices` is the source of truth; a stale tier price is ignored."""
    standard = await db.get(ModelTierConfig, ModelTier.STANDARD)
    assert standard is not None
    standard.model = "claude-sonnet-5-5"
    standard.input_cost_per_million_usd = 99.0
    await db.flush()

    cost = await PricingService(db).cost_cents(
        provider="anthropic",
        model="claude-sonnet-5-5",
        prompt_tokens=1_000_000,
        completion_tokens=0,
    )

    assert cost == pytest.approx(200.0)


async def test_a_new_price_applies_from_its_date_only(db: AsyncSession) -> None:
    now = datetime.now(UTC)
    db.add_all(
        [
            ModelPrice(
                provider="anthropic",
                model="claude-sonnet-5-5",
                input_usd_per_million=3.0,
                cached_input_usd_per_million=0.3,
                cache_write_usd_per_million=3.75,
                output_usd_per_million=15.0,
                effective_from=now - timedelta(minutes=1),
                source="test",
            ),
            ModelPrice(
                provider="anthropic",
                model="claude-sonnet-5-5",
                input_usd_per_million=9.0,
                cached_input_usd_per_million=0.9,
                cache_write_usd_per_million=9.0,
                output_usd_per_million=45.0,
                effective_from=now + timedelta(days=30),
                source="test",
            ),
        ]
    )
    await db.flush()
    service = PricingService(db)

    rates = await service.rates("anthropic", "claude-sonnet-5-5")
    october = await service.rates(
        "anthropic", "claude-sonnet-5-5", at=datetime(2026, 10, 19, 0, 0, 1, tzinfo=UTC)
    )

    assert rates is not None and rates.input == 3.0
    assert october is not None and october.input == 2.0


async def test_cache_writes_cost_more_than_fresh_input(db: AsyncSession) -> None:
    """Anthropic bills a 5-minute cache write at 1.25x input; it was billed 1x."""
    service = PricingService(db)

    cost = await service.cost_cents(
        provider="anthropic",
        model="claude-sonnet-5-5",
        prompt_tokens=1_000_000,
        completion_tokens=0,
        cached_tokens=400_000,
        cache_write_tokens=200_000,
    )

    # 400k fresh * $2 + 400k read * $0.10 + 200k written * $2.50 = $1.34.
    assert cost == pytest.approx(134.0)


async def test_haiku_5_5_costs_more_above_100k_tokens(db: AsyncSession) -> None:
    service = PricingService(db)

    short = await service.cost_cents(
        provider="anthropic",
        model="claude-haiku-5-5",
        prompt_tokens=100_000,
        completion_tokens=0,
    )
    long = await service.cost_cents(
        provider="anthropic",
        model="claude-haiku-5-5",
        prompt_tokens=200_000,
        completion_tokens=0,
    )

    assert short == pytest.approx(1.0)  # 100k * $0.10/M = $0.01
    assert long == pytest.approx(10.0)  # 200k * $0.50/M = $0.10


async def test_embeddings_and_anthropic_snapshots_are_priced(db: AsyncSession) -> None:
    service = PricingService(db)

    embed = await service.cost_cents(
        provider="openai",
        model="text-embedding-3-small",
        prompt_tokens=1_000_000,
        completion_tokens=0,
    )
    haiku = await service.cost_cents(
        provider="anthropic",
        model="claude-haiku-4-5-20251001",
        prompt_tokens=1_000_000,
        completion_tokens=0,
    )

    assert embed == pytest.approx(2.0)
    assert haiku == pytest.approx(100.0)
