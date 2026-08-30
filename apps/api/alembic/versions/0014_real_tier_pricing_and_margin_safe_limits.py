"""Real per-tier pricing, and plan limits that actually hold a margin.

Migration 0012 seeded ``model_tier_configs`` pricing at $0.0 on purpose ("an
operator sets real prices before the numbers this feeds mean anything") and
migration 0013 seeded ``plan_configs.monthly_ai_units`` at round, unvalidated
placeholders (200/1,000/3,000/8,000) with the same "not researched pricing"
caveat in its own comment. Nobody had set real numbers for either, so the
placeholder unit limits were never checked against real cost -- this migration
does both at once, since one without the other is meaningless.

Also adds ``plan_configs.monthly_price_cents`` (BRL cents), which didn't exist
until now -- the product's spec fixed R$29,90/59,90/99,90 for
student/pro/max in conversation, but nothing had ever persisted those numbers
anywhere; the margin math below needs a real price to check against, and
Phase 8 (Stripe) will need this same number as the source of truth for its
own Price objects rather than a second, possibly-drifting copy.

Pricing source: https://platform.claude.com/docs/en/about-claude/pricing,
fetched 2026-08-30 -- the exact model IDs 0012 already seeded (Claude Haiku
4.5 / Sonnet 5 / Opus 5):

  economy  (Haiku 4.5):  input $1/MTok,  cached-read $0.10/MTok, output $5/MTok
  standard (Sonnet 5):   input $2/MTok,  cached-read $0.20/MTok, output $10/MTok
  premium  (Opus 5):     input $5/MTok,  cached-read $0.50/MTok, output $25/MTok

Blended cost model (worst case, no prompt-caching credit taken -- a caching
deployment only ever costs *less* than this): assume 80% input / 20% output
tokens per call (a normal chat-completion shape), and a tier-usage mix of
10% economy / 80% standard / 10% premium, matching how the Professor
orchestrator (Phase 2) actually dispatches -- intent classification always
runs on the cheapest tier, most real actions run on standard, only "deepen"
escalates to premium:

  economy:  0.8*$1  + 0.2*$5  = $1.80 / M combined tokens
  standard: 0.8*$2  + 0.2*$10 = $3.60 / M combined tokens
  premium:  0.8*$5  + 0.2*$25 = $9.00 / M combined tokens
  blended:  0.10*1.80 + 0.80*3.60 + 0.10*9.00 = $3.96 / M combined tokens

1 AI Compute Unit = 1,000 combined tokens (``noema/services/entitlements.py``'s
``TOKENS_PER_UNIT``), so blended cost per unit rounds up to $0.004 -- a
deliberately conservative round number, not $0.00396 exactly.

Exchange rate: R$5.20/USD, an approximate, explicitly-labelled assumption as
of this calculation (2026-08-30) -- recompute if it moves materially, this is
not a live-fetched rate and this migration does not claim it is.

Worst case (100% of a plan's monthly units spent, every one on the average
blended mix above) against the BRL prices already fixed in the product spec
(R$29,90 / R$59,90 / R$99,90, unchanged by this migration -- only the unit
limits move):

  student: 300  units * $0.004 = $1.20 = R$6.24  -> 20.9% of R$29,90
  pro:     600  units * $0.004 = $2.40 = R$12.48 -> 20.8% of R$59,90
  max:     1000 units * $0.004 = $4.00 = R$20.80 -> 20.8% of R$99,90

Leaving payment fees (Stripe card 3.99% + R$0.39 fixed, Billing 0.7% --
``noema/services/economics.py``'s own defaults) on top, worst-case gross
margin still lands ~73-74% on every paid plan -- comfortable, not razor-thin,
even if every subscriber maxes out their plan every single month. Free stays
uncompared to any price (there is none), just a real, bounded cost-exposure
cap: 100 units = $0.40 = R$2.08/month per free account, still enough for a
real trial (~30-65 Professor turns), not a bait-and-switch teaser.

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

_TIER_ENUM = sa.Enum("economy", "standard", "premium", name="model_tier")
_PLAN_ENUM = sa.Enum("free", "student", "pro", "max", name="plan")

_TIER_TABLE = sa.table(
    "model_tier_configs",
    sa.column("tier", _TIER_ENUM),
    sa.column("input_cost_per_million_usd", sa.Float),
    sa.column("cached_input_cost_per_million_usd", sa.Float),
    sa.column("output_cost_per_million_usd", sa.Float),
)

_PLAN_TABLE = sa.table(
    "plan_configs",
    sa.column("plan", _PLAN_ENUM),
    sa.column("monthly_ai_units", sa.Integer),
    sa.column("monthly_price_cents", sa.Integer),
)

_TIER_PRICES = {
    "economy": (1.0, 0.10, 5.0),
    "standard": (2.0, 0.20, 10.0),
    "premium": (5.0, 0.50, 25.0),
}

#: (monthly_ai_units, monthly_price_cents). Prices are the ones already fixed
#: in the product spec (R$0 / R$29,90 / R$59,90 / R$99,90) -- unchanged by
#: this migration, only now actually persisted. Units are new, computed above.
_PLAN_CONFIG = {
    "free": (100, 0),
    "student": (300, 2_990),
    "pro": (600, 5_990),
    "max": (1000, 9_990),
}


def upgrade() -> None:
    conn = op.get_bind()
    for tier, (input_usd, cached_usd, output_usd) in _TIER_PRICES.items():
        conn.execute(
            _TIER_TABLE.update()
            .where(_TIER_TABLE.c.tier == tier)
            .values(
                input_cost_per_million_usd=input_usd,
                cached_input_cost_per_million_usd=cached_usd,
                output_cost_per_million_usd=output_usd,
            )
        )
    op.add_column(
        "plan_configs",
        sa.Column("monthly_price_cents", sa.Integer, nullable=False, server_default="0"),
    )
    for plan, (units, price_cents) in _PLAN_CONFIG.items():
        conn.execute(
            _PLAN_TABLE.update()
            .where(_PLAN_TABLE.c.plan == plan)
            .values(monthly_ai_units=units, monthly_price_cents=price_cents)
        )


def downgrade() -> None:
    conn = op.get_bind()
    for tier in _TIER_PRICES:
        conn.execute(
            _TIER_TABLE.update()
            .where(_TIER_TABLE.c.tier == tier)
            .values(
                input_cost_per_million_usd=0.0,
                cached_input_cost_per_million_usd=0.0,
                output_cost_per_million_usd=0.0,
            )
        )
    conn.execute(
        _PLAN_TABLE.update().values(
            monthly_ai_units=sa.case(
                (_PLAN_TABLE.c.plan == "free", 200),
                (_PLAN_TABLE.c.plan == "student", 1_000),
                (_PLAN_TABLE.c.plan == "pro", 3_000),
                (_PLAN_TABLE.c.plan == "max", 8_000),
            )
        )
    )
    op.drop_column("plan_configs", "monthly_price_cents")
