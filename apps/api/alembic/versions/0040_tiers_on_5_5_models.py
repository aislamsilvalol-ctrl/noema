"""The Anthropic tiers move to Haiku 5.5, Sonnet 5.5 and Opus 5.5.

Approved 2026-10-19 with the pricing plan (`docs/pricing/PRICING_AUDIT.md`).
Prices from https://platform.claude.com/docs/en/about-claude/pricing, fetched
2026-10-19, USD per million tokens (input / cache read / output):

  economy   claude-haiku-4-5-20251001  1 / 0.10 / 5
         -> claude-haiku-5-5           0.10 / 0.01 / 0.50
  standard  claude-sonnet-5            2 / 0.20 / 10
         -> claude-sonnet-5-5          2 / 0.10 / 10
  premium   claude-opus-5              5 / 0.50 / 25
         -> claude-opus-5-5            4 / 0.20 / 20

Haiku 4.5 is past its "not sooner than" retirement date; the 5.5 models are
cheaper or equal on every rate. The OpenAI side of each tier is unchanged
here (`services/professor.TIER_MODELS`).

Revision ID: 0040
Revises: 0039
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

NEW = {
    "economy": ("claude-haiku-5-5", 0.10, 0.01, 0.50),
    "standard": ("claude-sonnet-5-5", 2.00, 0.10, 10.00),
    "premium": ("claude-opus-5-5", 4.00, 0.20, 20.00),
}
OLD = {
    "economy": ("claude-haiku-4-5-20251001", 1.00, 0.10, 5.00),
    "standard": ("claude-sonnet-5", 2.00, 0.20, 10.00),
    "premium": ("claude-opus-5", 5.00, 0.50, 25.00),
}


def _set(rows: dict[str, tuple[str, float, float, float]]) -> None:
    for tier, (model, fresh, cached, out) in rows.items():
        op.execute(
            sa.text(
                "UPDATE model_tier_configs SET provider = 'anthropic', model = :model, "
                "input_cost_per_million_usd = :fresh, "
                "cached_input_cost_per_million_usd = :cached, "
                "output_cost_per_million_usd = :out, updated_at = now() "
                "WHERE tier = CAST(:tier AS model_tier)"
            ).bindparams(model=model, fresh=fresh, cached=cached, out=out, tier=tier)
        )


def upgrade() -> None:
    _set(NEW)


def downgrade() -> None:
    _set(OLD)
