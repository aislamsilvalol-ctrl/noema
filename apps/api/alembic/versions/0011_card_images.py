"""Image flashcards: an image attached to the front of a card.

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cards", sa.Column("front_image_key", sa.String(length=500), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("cards", "front_image_key")
