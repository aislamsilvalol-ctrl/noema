"""Journeys keep a curiosity parking lot (Focus mode).

Revision ID: 0021
Revises: 0020
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "learning_journeys",
        sa.Column("parked", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.alter_column("learning_journeys", "parked", server_default=None)


def downgrade() -> None:
    op.drop_column("learning_journeys", "parked")
