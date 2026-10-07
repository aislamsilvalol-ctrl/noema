"""Lesson lifecycle facts: started, completed, abandoned.

One small append-only table, idempotent on (owner, kind, source_id) the same
way `xp_events` is, so a retried request or a re-run sweep writes nothing twice.
Nothing is backfilled: the facts start from this deploy.

Revision ID: 0034
Revises: 0033
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column(
            "journey_id",
            UUID(as_uuid=True),
            sa.ForeignKey("learning_journeys.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("teaching_sessions.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("payload", JSONB(), nullable=False, server_default="{}"),
        sa.Column("source_id", sa.String(200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "owner_id", "kind", "source_id", name="uq_learning_events_source"
        ),
    )
    op.create_index(
        "ix_learning_events_owner_created",
        "learning_events",
        ["owner_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_learning_events_owner_created", table_name="learning_events")
    op.drop_table("learning_events")
