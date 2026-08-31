"""Stripe billing: customer linkage and idempotent webhook processing.

Adds ``users.stripe_customer_id`` (null until a user's first checkout succeeds --
which is every account today, since Stripe is unconfigured until an operator sets
real keys) and ``stripe_events`` (one row per processed webhook event id, so a
redelivered event no-ops instead of re-applying a plan change).

Revision ID: 0015
Revises: 0014
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
    )
    op.create_index("ix_users_stripe_customer_id", "users", ["stripe_customer_id"])
    op.create_table(
        "stripe_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("event_id", name="uq_stripe_events_event_id"),
    )


def downgrade() -> None:
    op.drop_table("stripe_events")
    op.drop_index("ix_users_stripe_customer_id", table_name="users")
    op.drop_column("users", "stripe_customer_id")
