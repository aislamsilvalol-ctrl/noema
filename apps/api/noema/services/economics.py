"""The Economics Simulator: a what-if calculator, not a report of real revenue.

There is no Stripe integration yet (deliberately last in this program), so there is
no real subscription revenue to report. Every number this module returns is a
projection from hypothetical inputs -- it reuses :class:`PricingService`'s real,
admin-editable per-tier pricing for the AI-cost side, because that part is real,
but the subscriber count, plan price, and fee percentages are always supplied by
the caller, never persisted, never presented as "current."
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import ModelTier
from noema.services.pricing import PricingService

#: Sane defaults from the product's own spec (Brazil, 2026-08-29): a national
#: card and Stripe Billing's own published rates. Callers can override every
#: one of these -- they are starting points for the form, not policy baked
#: into code, per this program's standing "never hardcode a number that moves
#: independently of the code" rule (established in Phase 1's pricing seed).
DEFAULT_PAYMENT_FEE_PERCENT = 3.99
DEFAULT_PAYMENT_FEE_FIXED_CENTS = 39.0
DEFAULT_BILLING_FEE_PERCENT = 0.7
DEFAULT_TAX_PERCENT = 0.0


@dataclass(frozen=True, slots=True)
class SimulatorInputs:
    subscribers: int
    messages_per_day: float
    avg_input_tokens: int
    avg_output_tokens: int
    #: Fraction of messages on each tier. Must sum to 1.0 (validated by the
    #: route's Pydantic model, not here -- this is the pure-math layer).
    tier_mix: dict[ModelTier, float]
    active_days_per_month: float
    plan_price_cents: float
    payment_fee_percent: float = DEFAULT_PAYMENT_FEE_PERCENT
    payment_fee_fixed_cents: float = DEFAULT_PAYMENT_FEE_FIXED_CENTS
    billing_fee_percent: float = DEFAULT_BILLING_FEE_PERCENT
    tax_percent: float = DEFAULT_TAX_PERCENT


@dataclass(frozen=True, slots=True)
class SimulatorResult:
    ai_cost_per_user_cents: float
    ai_cost_total_cents: float
    payment_fees_cents: float
    gross_revenue_cents: float
    net_revenue_cents: float
    gross_margin_percent: float
    #: A projection ("if this many subscribers pay this price"), never a
    #: live figure -- labelled as such at every layer that surfaces it.
    estimated_mrr_cents: float


class EconomicsSimulator:
    def __init__(self, session: AsyncSession) -> None:
        self.pricing = PricingService(session)

    async def _cost_per_message_cents(self, inputs: SimulatorInputs) -> float:
        """Blended AI cost of one message, weighted by the tier mix.

        Reuses :meth:`PricingService.cost_cents`'s exact math (not a parallel
        formula) so a change to how cost is computed can never silently
        diverge between what a user is actually charged for and what this
        simulator projects.
        """
        blended = 0.0
        for tier, share in inputs.tier_mix.items():
            if share <= 0:
                continue
            config = await self.pricing.tier_config(tier)
            if config is None:
                continue
            input_usd = (
                inputs.avg_input_tokens / 1_000_000
            ) * config.input_cost_per_million_usd
            output_usd = (
                inputs.avg_output_tokens / 1_000_000
            ) * config.output_cost_per_million_usd
            blended += share * (input_usd + output_usd) * 100
        return blended

    async def simulate(self, inputs: SimulatorInputs) -> SimulatorResult:
        cost_per_message_cents = await self._cost_per_message_cents(inputs)
        messages_per_user_per_month = (
            inputs.messages_per_day * inputs.active_days_per_month
        )
        ai_cost_per_user_cents = cost_per_message_cents * messages_per_user_per_month
        ai_cost_total_cents = ai_cost_per_user_cents * inputs.subscribers

        gross_revenue_cents = inputs.subscribers * inputs.plan_price_cents

        # One payment per subscriber per month -- the fixed per-transaction
        # fee is per subscriber, not per message.
        payment_fees_cents = inputs.subscribers * (
            inputs.plan_price_cents * (inputs.payment_fee_percent / 100)
            + inputs.payment_fee_fixed_cents
        )
        billing_fees_cents = gross_revenue_cents * (inputs.billing_fee_percent / 100)
        tax_cents = gross_revenue_cents * (inputs.tax_percent / 100)

        net_revenue_cents = (
            gross_revenue_cents
            - payment_fees_cents
            - billing_fees_cents
            - ai_cost_total_cents
            - tax_cents
        )
        gross_margin_percent = (
            (net_revenue_cents / gross_revenue_cents) * 100
            if gross_revenue_cents > 0
            else 0.0
        )

        return SimulatorResult(
            ai_cost_per_user_cents=ai_cost_per_user_cents,
            ai_cost_total_cents=ai_cost_total_cents,
            payment_fees_cents=payment_fees_cents + billing_fees_cents,
            gross_revenue_cents=gross_revenue_cents,
            net_revenue_cents=net_revenue_cents,
            gross_margin_percent=gross_margin_percent,
            estimated_mrr_cents=gross_revenue_cents,
        )
