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

from sqlalchemy import Float, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from noema.db.models import AIUsage, ModelTier, ModelTierConfig

#: 1 cent = 1_000_000 micro-cents. New rows store the integer; readers still
#: accept the legacy float on rows written before that column existed.
MICRO_CENTS_PER_CENT = 1_000_000

#: List prices (USD per million tokens: input, cached input, output) for models
#: that serve calls without a tier row of their own -- OpenAI answering a
#: request routed or failed over from Anthropic. A tier row, when one matches,
#: always wins; this only replaces a silent 0 for models known to cost money.
#: Check against the provider's price page when a model is added.
_LIST_PRICES: dict[tuple[str, str], tuple[float, float, float]] = {
    ("openai", "gpt-4.1"): (2.00, 0.50, 8.00),
    ("openai", "gpt-4.1-mini"): (0.40, 0.10, 1.60),
    ("openai", "gpt-4.1-nano"): (0.10, 0.025, 0.40),
}


#: A dated snapshot ("gpt-4.1-mini-2025-04-14") is the model it snapshots:
#: OpenAI answers with the dated name whatever alias the request used.
_SNAPSHOT = re.compile(r"-\d{4}-\d{2}-\d{2}$")


def list_price(provider: str, model: str) -> tuple[float, float, float] | None:
    """The published price of `model`, dated snapshot or alias."""
    return _LIST_PRICES.get((provider, model)) or _LIST_PRICES.get(
        (provider, _SNAPSHOT.sub("", model))
    )


def micro_cents_for_tokens(
    *,
    fresh_tokens: int,
    cached_tokens: int,
    completion_tokens: int,
    input_usd_per_million: float,
    cached_usd_per_million: float,
    output_usd_per_million: float,
) -> int:
    """USD-per-million rates to integer micro-cents.

    ``tokens * (usd / 1_000_000) * 100 cents * 1_000_000 micro-cents``
    simplifies to ``tokens * usd_per_million * 100``.
    """
    raw = (
        fresh_tokens * input_usd_per_million
        + cached_tokens * cached_usd_per_million
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

    async def cost_micro_cents(
        self,
        *,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int = 0,
    ) -> int:
        """0 for any (provider, model) that doesn't match a configured tier row --
        including every configured tier before an operator has set real prices, since
        rows are seeded at 0.0 on purpose (see ``ModelTierConfig``'s docstring). A
        silent 0 here is honest: it means "not priced yet," not "free."

        The unit is micro-cents (millionths of a cent), an integer, so a sum of
        many small calls does not drift the way a float of cents does.
        """
        result = await self.db.execute(
            select(ModelTierConfig).where(
                ModelTierConfig.provider == provider, ModelTierConfig.model == model
            )
        )
        config = result.scalars().first()
        cached = max(0, min(cached_tokens, prompt_tokens))
        fresh = prompt_tokens - cached
        if config is None:
            listed = list_price(provider, model)
            if listed is None:
                return 0
            input_rate, cached_rate, output_rate = listed
        else:
            # Cached input is billed at the cached rate when one is configured;
            # a tier seeded with 0.0 for it charges cached tokens at the full
            # rate — the honest direction to be wrong in, never a free ride.
            input_rate = config.input_cost_per_million_usd
            cached_rate = config.cached_input_cost_per_million_usd or input_rate
            output_rate = config.output_cost_per_million_usd
        return micro_cents_for_tokens(
            fresh_tokens=fresh,
            cached_tokens=cached,
            completion_tokens=completion_tokens,
            input_usd_per_million=input_rate,
            cached_usd_per_million=cached_rate,
            output_usd_per_million=output_rate,
        )

    async def cost_cents(
        self,
        *,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int = 0,
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
        )
        return cents_from_micro_cents(micro)
