"""Socratic dialogues, alongside written explanations.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    kind = sa.Enum("feynman", "socratic", name="explanation_kind")
    kind.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "explanations",
        # Existing rows are all written explanations, which is what the table held
        # before this column existed.
        sa.Column("kind", kind, nullable=False, server_default="feynman"),
    )
    op.add_column(
        "explanations",
        sa.Column("transcript", JSONB(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("explanations", "transcript")
    op.drop_column("explanations", "kind")
    sa.Enum(name="explanation_kind").drop(op.get_bind(), checkfirst=True)
