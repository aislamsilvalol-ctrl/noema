"""Request ids on AI usage rows.

Every request now carries an id (accepted from a sane `X-Request-ID` or
generated), bound into the logs and handed to jobs it enqueues. Storing it on
`ai_usage` ties a cost row to the log lines that explain it. Nullable: rows
written before this, and calls made outside any request, have none.

Numbered after `0032_focus_sessions` (being built in parallel); if that lands
under a different revision id, only `down_revision` here needs to change.

Revision ID: 0033
Revises: 0032
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_usage", sa.Column("request_id", sa.String(128), nullable=True))
    op.create_index("ix_ai_usage_request_id", "ai_usage", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_request_id", table_name="ai_usage")
    op.drop_column("ai_usage", "request_id")
