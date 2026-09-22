"""Idempotency key on reviews.

A review flushed from the offline queue was applied every time it arrived:
`record_review` wrote a fresh evidence row and advanced the schedule, so a
retry after a timeout the server had in fact committed, a second tab, or a
reload mid-flush all pushed the card to an interval the learner never earned.
The client's own id for the attempt makes the write once-only. See
`noema.db.models.Review.client_event_id`.

Revision ID: 0024
Revises: 0023
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reviews",
        sa.Column("client_event_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    # Nulls are distinct in Postgres, so every existing review -- and every one
    # from a client that sends no key -- keeps working untouched.
    op.create_unique_constraint(
        "uq_reviews_client_event", "reviews", ["owner_id", "client_event_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_reviews_client_event", "reviews", type_="unique")
    op.drop_column("reviews", "client_event_id")
