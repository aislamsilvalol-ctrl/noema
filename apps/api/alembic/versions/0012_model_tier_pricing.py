"""Model-tier config: which model backs each cost tier, and what it costs.

Seeds three rows (economy/standard/premium) pointing at the Anthropic model IDs
this session has verified as current -- the only provider with a confirmed,
authoritative current lineup available while writing this migration. Pricing
columns are seeded at 0.0 on purpose; see ModelTierConfig's docstring in
noema/db/models.py.

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

_TIER_ENUM = sa.Enum("economy", "standard", "premium", name="model_tier")

_TABLE = sa.table(
    "model_tier_configs",
    sa.column("tier", _TIER_ENUM),
    sa.column("provider", sa.String),
    sa.column("model", sa.String),
    sa.column("input_cost_per_million_usd", sa.Float),
    sa.column("cached_input_cost_per_million_usd", sa.Float),
    sa.column("output_cost_per_million_usd", sa.Float),
)


def upgrade() -> None:
    # No explicit .create() here, unlike an ADD COLUMN migration (e.g. 0008) --
    # op.create_table's own DDL creates a brand-new enum type as part of creating
    # the table itself. Calling .create() first as well double-creates it and the
    # second attempt fails with "type already exists" in a single process, the
    # exact class of bug the CI job below this one exists to catch (see 0007's
    # incident note in ci.yml).
    op.create_table(
        "model_tier_configs",
        sa.Column("tier", _TIER_ENUM, primary_key=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column(
            "input_cost_per_million_usd", sa.Float, nullable=False, server_default="0.0"
        ),
        sa.Column(
            "cached_input_cost_per_million_usd",
            sa.Float,
            nullable=False,
            server_default="0.0",
        ),
        sa.Column(
            "output_cost_per_million_usd", sa.Float, nullable=False, server_default="0.0"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.bulk_insert(
        _TABLE,
        [
            {
                "tier": "economy",
                "provider": "anthropic",
                "model": "claude-haiku-4-5-20251001",
                "input_cost_per_million_usd": 0.0,
                "cached_input_cost_per_million_usd": 0.0,
                "output_cost_per_million_usd": 0.0,
            },
            {
                "tier": "standard",
                "provider": "anthropic",
                "model": "claude-sonnet-5",
                "input_cost_per_million_usd": 0.0,
                "cached_input_cost_per_million_usd": 0.0,
                "output_cost_per_million_usd": 0.0,
            },
            {
                "tier": "premium",
                "provider": "anthropic",
                "model": "claude-opus-5",
                "input_cost_per_million_usd": 0.0,
                "cached_input_cost_per_million_usd": 0.0,
                "output_cost_per_million_usd": 0.0,
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("model_tier_configs")
    _TIER_ENUM.drop(op.get_bind(), checkfirst=True)
