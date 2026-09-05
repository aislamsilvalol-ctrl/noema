"""Memory summaries carry an embedding, for relevance-ordered retrieval.

Revision ID: 0020
Revises: 0019
"""

from __future__ import annotations

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op
from noema.core.config import get_settings

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "memory_summaries",
        sa.Column("embedding", Vector(get_settings().noema_embedding_dim)),
    )
    op.add_column("memory_summaries", sa.Column("embedding_model", sa.String(100)))


def downgrade() -> None:
    op.drop_column("memory_summaries", "embedding_model")
    op.drop_column("memory_summaries", "embedding")
