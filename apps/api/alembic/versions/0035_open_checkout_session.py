"""Remember an unsettled Stripe Checkout Session on the user.

A second checkout click, before the webhook has written ``users.plan``,
would otherwise open another Subscription. The session id is enough to
ask Stripe whether that attempt is still open. Null for every account
that has never started checkout.

Revision ID: 0035
Revises: 0034
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("open_checkout_session_id", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "open_checkout_session_id")
