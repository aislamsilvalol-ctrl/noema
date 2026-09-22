"""Observed difficulty on questions.

`questions.difficulty` is what the author declared. If nine beginners in ten
get a "hard" item right, it is not hard, and the mastery engine was weighting
it as if it were. These two columns hold what learners actually showed: a
smoothed wrong-answer rate over the `answers` log, and how many answers it
rests on. See `noema.engines.difficulty`.

Revision ID: 0025
Revises: 0024
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable, no default: a question nobody has answered has no observed
    # difficulty, and pretending otherwise is the thing this is meant to stop.
    op.add_column(
        "questions", sa.Column("observed_difficulty", sa.Float(), nullable=True)
    )
    op.add_column("questions", sa.Column("observed_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("questions", "observed_count")
    op.drop_column("questions", "observed_difficulty")
