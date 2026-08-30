"""Plan entitlements: what each subscription tier allows, decoupled from Stripe.

Creates plan_configs (one row per plan, seeded with placeholder monthly AI Compute
Unit limits an operator adjusts once real numbers exist) and adds users.plan,
defaulting every existing and future account to 'free' -- there is no billing yet
to have set anything else.

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PGENUM

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

#: Created below by op.create_table's own DDL. users.plan reuses it --
#: create_type=False, or this dies on DuplicateObject the way 0007 once did
#: (see that migration's own comment; only postgresql.ENUM honours the kwarg,
#: sa.Enum silently drops it).
_PLAN_ENUM = sa.Enum("free", "student", "pro", "max", name="plan")
_PLAN_ENUM_REUSE = PGENUM("free", "student", "pro", "max", name="plan", create_type=False)

_TABLE = sa.table(
    "plan_configs",
    sa.column("plan", _PLAN_ENUM),
    sa.column("monthly_ai_units", sa.Integer),
)


def upgrade() -> None:
    op.create_table(
        "plan_configs",
        sa.Column("plan", _PLAN_ENUM, primary_key=True),
        sa.Column("monthly_ai_units", sa.Integer, nullable=False),
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
            # Placeholder limits, not researched pricing -- an operator sets real
            # ones once real usage/cost data exists (same discipline as 0012's
            # pricing columns being seeded at 0.0 rather than a guessed figure).
            # 1 AI Compute Unit = 1,000 tokens (noema/services/entitlements.py).
            {"plan": "free", "monthly_ai_units": 200},
            {"plan": "student", "monthly_ai_units": 1_000},
            {"plan": "pro", "monthly_ai_units": 3_000},
            {"plan": "max", "monthly_ai_units": 8_000},
        ],
    )
    op.add_column(
        "users",
        sa.Column("plan", _PLAN_ENUM_REUSE, nullable=False, server_default="free"),
    )


def downgrade() -> None:
    op.drop_column("users", "plan")
    op.drop_table("plan_configs")
    _PLAN_ENUM.drop(op.get_bind(), checkfirst=True)
