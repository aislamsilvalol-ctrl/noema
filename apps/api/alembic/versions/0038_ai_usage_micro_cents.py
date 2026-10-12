"""Integer micro-cents beside the legacy float cost.

`ai_usage.cost_cents` stays. Rows already written keep their float and leave
this column null; readers fall back to the float for those. New rows write
both, and the integer is what a sum uses when it is present. Nothing here
rewrites history.

Revision ID: 0038
Revises: 0037
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_usage",
        sa.Column("cost_micro_cents", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ai_usage", "cost_micro_cents")
