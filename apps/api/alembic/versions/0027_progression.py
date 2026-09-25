"""Progression: XP earned from real learning events.

Revision ID: 0027
Revises: 0026
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "xp_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("source_id", sa.String(160), nullable=False),
        sa.Column("xp", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detail", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("owner_id", "kind", "source_id", name="uq_xp_events_source"),
    )
    op.create_index(
        "ix_xp_events_owner_occurred", "xp_events", ["owner_id", "occurred_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_xp_events_owner_occurred", table_name="xp_events")
    op.drop_table("xp_events")
