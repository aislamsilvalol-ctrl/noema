"""Timed exams, graded only at the end.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exams",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column(
            "notebook_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("notebooks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("minutes", sa.Integer(), nullable=False),
        # The set is fixed when the exam starts: one that can change while it is
        # being taken measures nothing.
        sa.Column("question_ids", JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("score", sa.Float()),
        sa.Column(
            "overtime", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("results", JSONB(), nullable=False, server_default="{}"),
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
    op.create_index("ix_exams_owner_id", "exams", ["owner_id"])
    op.create_index("ix_exams_notebook_id", "exams", ["notebook_id"])
    op.create_index("ix_exams_started_at", "exams", ["started_at"])


def downgrade() -> None:
    op.drop_table("exams")
