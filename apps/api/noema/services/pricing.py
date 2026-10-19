"""Turns token counts into a dollar figure, and looks up what a tier points at.

Providers report tokens, not cost -- ``Usage.cost_cents`` (``noema/providers/base.py``)
has never actually been populated by any provider, so every ``AIUsage`` row written
before this module existed had ``cost_cents == 0.0`` regardless of what was spent.
Pricing is a config concern (it moves independently of provider wiring, and per the
product's own requirement has to be editable without a redeploy), so it is computed
here, once, at the point usage is recorded -- not duplicated into every provider.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Float, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from noema.db.models import AIUsage, ModelPrice, ModelTier, ModelTierConfig

#: 1 cent = 1_000_000 micro-cents. New rows store the integer; readers still
#: accept the legacy float on rows written before that column existed.
MICRO_CENTS_PER_CENT = 1_000_000

#: List prices (USD per million tokens: input, cached input, output), the
#: last resort when `model_prices` has no row for a model and no tier row
#: matches either (a database seeded before 0039, a test without it). The
#: table is the source of truth; keep this in step with migration 0039.
_LIST_PRICES: dict[tuple[str, str], tuple[float, float, float]] = {
    ("anthropic", "claude-haiku-5-5"): (0.10, 0.01, 0.50),
    ("anthropic", "claude-sonnet-5-5"): (2.00, 0.10, 10.00),
    ("anthropic", "claude-opus-5-5"): (4.00, 0.20, 20.00),
    ("anthropic", "claude-sonnet-4-5"): (3.00, 0.30, 15.00),
    ("openai", "gpt-4.1"): (2.00, 0.50, 8.00),
    ("openai", "gpt-4.1-mini"): (0.40, 0.10, 1.60),
    ("openai", "gpt-4.1-nano"): (0.10, 0.025, 0.40),
    ("openai", "text-embedding-3-small"): (0.02, 0.02, 0.0),
}

#: Anthropic bills a 5-minute cache write at 1.25x the input price.
CACHE_WRITE_MULTIPLIER = 1.25


#: A dated snapshot ("gpt-4.1-mini-2025-04-14", "claude-haiku-4-5-20251001")
#: is the model it snapshots: providers answer with the dated name whatever
#: alias the request used.
_SNAPSHOT = re.compile(r"-(\d{4}-\d{2}-\d{2}|\d{8})$")


def base_model(model: str) -> str:
    """`model` without a dated snapshot suffix."""
    return _SNAPSHOT.sub("", model)


def list_price(provider: str, model: str) -> tuple[float, float, float] | None:
    """The published price of `model`, dated snapshot or alias."""
    return _LIST_PRICES.get((provider, model)) or _LIST_PRICES.get(
        (provider, base_model(model))
    )


@dataclass(frozen=True, slots=True)
class Rates:
    """USD per million tokens."""

    input: float
    cached: float
    cache_write: float
    output: float
    long_context_threshold: int | None = None
    long_context_multiplier: float | None = None

    def scaled_for(self, prompt_tokens: int) -> Rates:
        """The rates for a prompt this long (Haiku 5.5 costs 5x above 100K)."""
        if (
            self.long_context_threshold is None
            or self.long_context_multiplier is None
            or prompt_tokens <= self.long_context_threshold
        ):
            return self
        m = self.long_context_multiplier
        return Rates(
            self.input * m, self.cached * m, self.cache_write * m, self.output * m
        )


def micro_cents_for_tokens(
    *,
    fresh_tokens: int,
    cached_tokens: int,
    completion_tokens: int,
    input_usd_per_million: float,
    cached_usd_per_million: float,
    output_usd_per_million: float,
    cache_write_tokens: int = 0,
    cache_write_usd_per_million: float = 0.0,
) -> int:
    """USD-per-million rates to integer micro-cents.

    ``tokens * (usd / 1_000_000) * 100 cents * 1_000_000 micro-cents``
    simplifies to ``tokens * usd_per_million * 100``.
    """
    raw = (
        fresh_tokens * input_usd_per_million
        + cached_tokens * cached_usd_per_million
        + cache_write_tokens * cache_write_usd_per_million
        + completion_tokens * output_usd_per_million
    ) * 100
    return round(raw)


def cents_from_micro_cents(micro_cents: int) -> float:
    """The legacy float column, derived from the integer so the two cannot drift."""
    return micro_cents / MICRO_CENTS_PER_CENT


def stored_cost_cents() -> ColumnElement[float]:
    """Cents for a row: integer micro-cents when written, else the legacy float."""
    micro = cast(AIUsage.cost_micro_cents, Float) / float(MICRO_CENTS_PER_CENT)
    return func.coalesce(micro, AIUsage.cost_cents)


class PricingService:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    async def tier_config(self, tier: ModelTier) -> ModelTierConfig | None:
        return await self.db.get(ModelTierConfig, tier)

    async def all_tiers(self) -> list[ModelTierConfig]:
        result = await self.db.execute(
            select(ModelTierConfig).order_by(ModelTierConfig.tier)
        )
        return list(result.scalars().all())

    async def rates(
        self, provider: str, model: str, *, at: datetime | None = None
    ) -> Rates | None:
        """What `model` costs, newest price in force first: `model_prices`,
        then a tier row, then the list in code. None when nobody knows."""
        when = at or datetime.now(UTC)
        names = {model, base_model(model)}
        price = (
            await self.db.execute(
                select(ModelPrice)
                .where(
                    ModelPrice.provider == provider,
                    ModelPrice.model.in_(names),
                    ModelPrice.effective_from <= when,
                )
                .order_by(ModelPrice.effective_from.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if price is not None:
            return Rates(
                price.input_usd_per_million,
                price.cached_input_usd_per_million,
                price.cache_write_usd_per_million,
                price.output_usd_per_million,
                price.long_context_threshold,
                price.long_context_multiplier,
            )

        config = (
            (
                await self.db.execute(
                    select(ModelTierConfig).where(
                        ModelTierConfig.provider == provider,
                        ModelTierConfig.model.in_(names),
                    )
                )
            )
            .scalars()
            .first()
        )
        if config is not None:
            # Cached input is billed at the cached rate when one is configured;
            # a tier seeded with 0.0 for it charges cached tokens at the full
            # rate — the honest direction to be wrong in, never a free ride.
            fresh = config.input_cost_per_million_usd
            return Rates(
                fresh,
                config.cached_input_cost_per_million_usd or fresh,
                fresh * CACHE_WRITE_MULTIPLIER,
                config.output_cost_per_million_usd,
            )

        listed = list_price(provider, model)
        if listed is None:
            return None
        fresh, cached, output = listed
        return Rates(fresh, cached, fresh * CACHE_WRITE_MULTIPLIER, output)

    async def cost_micro_cents(
        self,
        *,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> int:
        """0 for a (provider, model) no price list knows. A silent 0 here
        means "not priced yet," not "free"; `unpriced` in the ops view counts
        those rows.

        The unit is micro-cents (millionths of a cent), an integer, so a sum of
        many small calls does not drift the way a float of cents does.
        """
        rates = await self.rates(provider, model)
        if rates is None:
            return 0
        rates = rates.scaled_for(prompt_tokens)
        cached = max(0, min(cached_tokens, prompt_tokens))
        written = max(0, min(cache_write_tokens, prompt_tokens - cached))
        return micro_cents_for_tokens(
            fresh_tokens=prompt_tokens - cached - written,
            cached_tokens=cached,
            completion_tokens=completion_tokens,
            input_usd_per_million=rates.input,
            cached_usd_per_million=rates.cached,
            output_usd_per_million=rates.output,
            cache_write_tokens=written,
            cache_write_usd_per_million=rates.cache_write,
        )

    async def cost_cents(
        self,
        *,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> float:
        """The same figure as :meth:`cost_micro_cents`, in cents.

        Derived from the integer so callers that still read a float see the
        value that was stored, not a second rounding of the rates.
        """
        micro = await self.cost_micro_cents(
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            cache_write_tokens=cache_write_tokens,
        )
        return cents_from_micro_cents(micro)
