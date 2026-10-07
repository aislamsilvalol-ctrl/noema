"""Focus sessions: Modo TDAH's short sittings, remembered server-side.

One row per sitting — its kind, its plan (minutes, steps) and how far it got.
The learning itself is written where it always was (lesson turns, reviews,
the student model); this table only holds the sitting's shape, so a refresh
or another device resumes on the same step. A partial unique index keeps at
most one active-or-paused sitting per learner.

Revision ID: 0032
Revises: 0031
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "focus_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column(
            "journey_id",
            UUID(as_uuid=True),
            sa.ForeignKey("learning_journeys.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "teaching_session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("teaching_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(200), nullable=False, server_default=""),
        sa.Column("concept", sa.String(200), nullable=False, server_default=""),
        sa.Column("planned_minutes", sa.Integer(), nullable=False),
        sa.Column("steps_total", sa.Integer(), nullable=False),
        sa.Column("steps_done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
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
    op.create_index(
        "uq_focus_sessions_owner_open",
        "focus_sessions",
        ["owner_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('active', 'paused')"),
    )


def downgrade() -> None:
    op.drop_index("uq_focus_sessions_owner_open", table_name="focus_sessions")
    op.drop_table("focus_sessions")
