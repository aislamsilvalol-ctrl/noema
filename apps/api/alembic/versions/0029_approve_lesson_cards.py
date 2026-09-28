"""Approve the cards Mino already wrote inside lessons.

New lesson cards are approved at birth; these older ones waited for an
in-chat flip that most never got, so /review never saw them.

Revision ID: 0029
Revises: 0028
"""

from __future__ import annotations

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE cards SET approved_at = created_at "
        "WHERE journey_id IS NOT NULL AND approved_at IS NULL AND deleted_at IS NULL"
    )


def downgrade() -> None:
    # Which rows this touched is not recorded; approval is not undone.
    pass
