"""Turns token counts into a dollar figure, and looks up what a tier points at.

Providers report tokens, not cost -- ``Usage.cost_cents`` (``noema/providers/base.py``)
has never actually been populated by any provider, so every ``AIUsage`` row written
before this module existed had ``cost_cents == 0.0`` regardless of what was spent.
Pricing is a config concern (it moves independently of provider wiring, and per the
product's own requirement has to be editable without a redeploy), so it is computed
here, once, at the point usage is recorded -- not duplicated into every provider.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import ModelTier, ModelTierConfig


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

    async def cost_cents(
        self, *, provider: str, model: str, prompt_tokens: int, completion_tokens: int
    ) -> float:
        """0.0 for any (provider, model) that doesn't match a configured tier row --
        including every configured tier before an operator has set real prices, since
        rows are seeded at 0.0 on purpose (see ``ModelTierConfig``'s docstring). A
        silent 0 here is honest: it means "not priced yet," not "free."
        """
        result = await self.db.execute(
            select(ModelTierConfig).where(
                ModelTierConfig.provider == provider, ModelTierConfig.model == model
            )
        )
        config = result.scalars().first()
        if config is None:
            return 0.0
        input_cost_usd = (prompt_tokens / 1_000_000) * config.input_cost_per_million_usd
        output_cost_usd = (
            completion_tokens / 1_000_000
        ) * config.output_cost_per_million_usd
        return (input_cost_usd + output_cost_usd) * 100
