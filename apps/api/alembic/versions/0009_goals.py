"""Goals with a date on them.

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "goals",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "notebook_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("notebooks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("target_mastery", sa.Float(), nullable=False, server_default="80"),
        sa.Column("minutes_per_day", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("achieved_at", sa.DateTime(timezone=True)),
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
    op.create_index("ix_goals_owner_id", "goals", ["owner_id"])
    op.create_index("ix_goals_notebook_id", "goals", ["notebook_id"])
    op.create_index("ix_goals_due_on", "goals", ["due_on"])


def downgrade() -> None:
    op.drop_table("goals")
