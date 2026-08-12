"""Stored study sessions.

Revision ID: 0005
Revises: 0004

The plan is kept verbatim alongside what happened, because a scheduler change that
cannot be replayed against real history can only be asserted. Every constant in
``SchedulerSettings`` is a hypothesis waiting on these rows.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "study_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("planned_minutes", sa.Integer, nullable=False),
        sa.Column("estimated_seconds", sa.Float, nullable=False, server_default="0"),
        sa.Column("actual_seconds", sa.Float),
        sa.Column("rationale", sa.Text, nullable=False, server_default=""),
        sa.Column("plan", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("items_planned", sa.Integer, nullable=False, server_default="0"),
        sa.Column("items_completed", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
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
    op.create_index("ix_study_sessions_owner_id", "study_sessions", ["owner_id"])
    op.create_index("ix_study_sessions_started_at", "study_sessions", ["started_at"])


def downgrade() -> None:
    op.drop_table("study_sessions")
