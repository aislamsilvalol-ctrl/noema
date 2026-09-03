"""Teaching sessions and turns: the lesson, remembered.

Revision ID: 0017
Revises: 0016
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

#: New in this revision, so it is created here (and dropped in downgrade). A
#: later migration that references it must use postgresql.ENUM(...,
#: create_type=False) — see tests/test_migrations.py for why.
TURN_ROLE = sa.Enum("learner", "noema", name="teaching_turn_role")


def upgrade() -> None:
    op.create_table(
        "teaching_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "notebook_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notebooks.id", ondelete="SET NULL"),
        ),
        sa.Column("learning_goal", sa.Text(), nullable=False),
        sa.Column("session_goal", sa.Text(), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("current_topic", sa.String(200), nullable=False),
        sa.Column(
            "current_concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("current_concept", sa.String(200), nullable=False),
        sa.Column("learner_level", sa.String(32), nullable=False),
        sa.Column("depth", sa.String(32), nullable=False),
        sa.Column("strategy", sa.String(48), nullable=False),
        sa.Column("plan", postgresql.JSONB(), nullable=False),
        sa.Column("understanding", postgresql.JSONB(), nullable=False),
        sa.Column("misconceptions", postgresql.JSONB(), nullable=False),
        sa.Column("turn_count", sa.Integer(), nullable=False),
        sa.Column("last_turn_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
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
    op.create_index("ix_teaching_sessions_owner_id", "teaching_sessions", ["owner_id"])
    op.create_index(
        "ix_teaching_sessions_notebook_id", "teaching_sessions", ["notebook_id"]
    )
    op.create_index(
        "ix_teaching_sessions_owner_last",
        "teaching_sessions",
        ["owner_id", "last_turn_at"],
    )

    op.create_table(
        "teaching_turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teaching_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", TURN_ROLE, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(48), nullable=False),
        sa.Column("decision", postgresql.JSONB()),
        sa.Column("pedagogy", postgresql.JSONB()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_teaching_turns_owner_id", "teaching_turns", ["owner_id"])
    op.create_index("ix_teaching_turns_session_id", "teaching_turns", ["session_id"])
    op.create_index("ix_teaching_turns_created_at", "teaching_turns", ["created_at"])


def downgrade() -> None:
    op.drop_table("teaching_turns")
    op.drop_table("teaching_sessions")
    TURN_ROLE.drop(op.get_bind(), checkfirst=True)
