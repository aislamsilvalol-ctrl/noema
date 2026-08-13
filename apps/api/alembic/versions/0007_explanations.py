"""Feynman explanations, kept as evidence.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "explanations",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "concept_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("concepts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Verbatim: months later the useful thing is not the score, it is reading
        # what you used to think.
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "grader",
            sa.Enum("deterministic", "ai", "self", name="grader", create_type=False),
            nullable=False,
            server_default="ai",
        ),
        sa.Column("findings", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "explained_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
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
    op.create_index("ix_explanations_owner_id", "explanations", ["owner_id"])
    op.create_index("ix_explanations_concept_id", "explanations", ["concept_id"])
    op.create_index("ix_explanations_explained_at", "explanations", ["explained_at"])


def downgrade() -> None:
    op.drop_table("explanations")
