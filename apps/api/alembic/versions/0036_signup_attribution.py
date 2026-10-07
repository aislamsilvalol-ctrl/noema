"""Where a signup came from: the landing page's UTM tags, kept on the account.

One nullable JSON column. The browser keeps the first visit's
utm_source/medium/campaign/content and sends them with the registration; the
server keeps only those four keys, as short strings. Null for every account
that predates this and for every signup that arrived without tags.

Revision ID: 0036
Revises: 0035
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("signup_attribution", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "signup_attribution")
