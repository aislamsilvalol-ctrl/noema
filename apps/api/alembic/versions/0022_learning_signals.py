"""Mastery events carry the signals a learner model needs.

A stable concept id, the item answered, time to answer, item difficulty,
the learner's stated confidence and the teaching session — and the
projection version on the concept state. Phase 0 of Aquilante:
start collecting what the model will read.

Revision ID: 0022
Revises: 0021
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mastery_events",
        sa.Column(
            "concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("concepts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_mastery_events_concept_id", "mastery_events", ["concept_id"])
    op.add_column(
        "mastery_events",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teaching_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("mastery_events", sa.Column("item_id", sa.String(160), nullable=True))
    op.add_column("mastery_events", sa.Column("elapsed_ms", sa.Integer(), nullable=True))
    op.add_column("mastery_events", sa.Column("difficulty", sa.Float(), nullable=True))
    op.add_column("mastery_events", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column(
        "student_concept_states", sa.Column("model_version", sa.String(32), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("student_concept_states", "model_version")
    for col in ("confidence", "difficulty", "elapsed_ms", "item_id", "session_id"):
        op.drop_column("mastery_events", col)
    op.drop_index("ix_mastery_events_concept_id", table_name="mastery_events")
    op.drop_column("mastery_events", "concept_id")
