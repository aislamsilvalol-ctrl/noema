"""Versioned model prices, cache writes, and usage rows without an account.

`model_prices` is the price list the cost of every AI call is read from. A
price change is a new row with a later `effective_from`, never an edit, so a
past month can always be recomputed at the price that was in force. The
tier table (`model_tier_configs`) still says which model serves a tier; its
price columns are now only a fallback for a model this table does not list.

Seeded from the official price pages, fetched 2026-10-19 (see
`docs/pricing/market-2026-10-19.md`):

  https://platform.claude.com/docs/en/about-claude/pricing
  https://developers.openai.com/api/docs/pricing

USD per million tokens: input / cache read / cache write (5 min) / output.
Haiku 5.5 is priced by prompt length: above 100K tokens every rate is 5x.

`ai_usage.cache_write_tokens`: Anthropic bills a cache write at 1.25x input,
and that was priced at 1x. `ai_usage.owner_id` becomes nullable so the
landing demo, which has no account, can write the rows it never wrote.

Revision ID: 0039
Revises: 0038
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

ANTHROPIC = "https://platform.claude.com/docs/en/about-claude/pricing"
OPENAI = "https://developers.openai.com/api/docs/pricing"
FETCHED = datetime(2026, 10, 19, tzinfo=UTC)

# provider, model, input, cache read, cache write, output, long threshold, long multiplier
PRICES: list[tuple[str, str, float, float, float, float, int | None, float | None]] = [
    ("anthropic", "claude-haiku-5-5", 0.10, 0.01, 0.125, 0.50, 100_000, 5.0),
    ("anthropic", "claude-sonnet-5-5", 2.00, 0.10, 2.50, 10.00, None, None),
    ("anthropic", "claude-opus-5-5", 4.00, 0.20, 5.00, 20.00, None, None),
    ("anthropic", "claude-haiku-4-5", 1.00, 0.10, 1.25, 5.00, None, None),
    ("anthropic", "claude-sonnet-5", 2.00, 0.20, 2.50, 10.00, None, None),
    ("anthropic", "claude-opus-5", 5.00, 0.50, 6.25, 25.00, None, None),
    ("anthropic", "claude-sonnet-4-5", 3.00, 0.30, 3.75, 15.00, None, None),
    ("openai", "gpt-4.1", 2.00, 0.50, 2.00, 8.00, None, None),
    ("openai", "gpt-4.1-mini", 0.40, 0.10, 0.40, 1.60, None, None),
    ("openai", "gpt-4.1-nano", 0.10, 0.025, 0.10, 0.40, None, None),
    ("openai", "gpt-6-luna", 0.10, 0.01, 0.125, 0.50, None, None),
    ("openai", "gpt-5.6-luna", 0.20, 0.02, 0.25, 1.20, None, None),
    ("openai", "gpt-5.6-terra", 2.00, 0.20, 2.50, 12.00, None, None),
    ("openai", "gpt-5.6-sol", 4.00, 0.40, 5.00, 20.00, None, None),
    ("openai", "text-embedding-3-small", 0.02, 0.02, 0.02, 0.0, None, None),
    ("openai", "text-embedding-3-large", 0.13, 0.13, 0.13, 0.0, None, None),
]


def upgrade() -> None:
    table = op.create_table(
        "model_prices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("input_usd_per_million", sa.Float(), nullable=False),
        sa.Column("cached_input_usd_per_million", sa.Float(), nullable=False),
        sa.Column("cache_write_usd_per_million", sa.Float(), nullable=False),
        sa.Column("output_usd_per_million", sa.Float(), nullable=False),
        sa.Column("long_context_threshold", sa.Integer(), nullable=True),
        sa.Column("long_context_multiplier", sa.Float(), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(300), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("provider", "model", "effective_from"),
    )
    op.create_index(
        "ix_model_prices_lookup", "model_prices", ["provider", "model", "effective_from"]
    )
    op.bulk_insert(
        table,
        [
            {
                "id": uuid.uuid4(),
                "provider": provider,
                "model": model,
                "input_usd_per_million": fresh,
                "cached_input_usd_per_million": cached,
                "cache_write_usd_per_million": write,
                "output_usd_per_million": out,
                "long_context_threshold": threshold,
                "long_context_multiplier": multiplier,
                "effective_from": FETCHED,
                "source": ANTHROPIC if provider == "anthropic" else OPENAI,
            }
            for provider, model, fresh, cached, write, out, threshold, multiplier in (
                PRICES
            )
        ],
    )

    op.add_column(
        "ai_usage",
        sa.Column("cache_write_tokens", sa.Integer(), server_default="0", nullable=False),
    )
    op.alter_column("ai_usage", "owner_id", nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM ai_usage WHERE owner_id IS NULL")
    op.alter_column("ai_usage", "owner_id", nullable=False)
    op.drop_column("ai_usage", "cache_write_tokens")
    op.drop_index("ix_model_prices_lookup", table_name="model_prices")
    op.drop_table("model_prices")
