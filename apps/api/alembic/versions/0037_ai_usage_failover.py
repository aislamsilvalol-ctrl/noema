"""Which provider an AI call failed over from.

With providers interleaved (`NOEMA_AI_ROUTING`) the ops view splits the last
day per provider: calls served, calls it lost to another provider, errors.
`provider` already says who served a row; this says who was meant to, when
that was someone else. Null for a call its first-choice provider answered,
and for every row written before this.

Revision ID: 0037
Revises: 0036
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_usage", sa.Column("failed_over_from", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_usage", "failed_over_from")
