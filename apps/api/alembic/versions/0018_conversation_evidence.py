"""Conversation as evidence: a third kind of explanation.

Revision ID: 0018
Revises: 0017
"""

from __future__ import annotations

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extending an existing type, not creating one — so neither sa.Enum nor
    # postgresql.ENUM is involved (see tests/test_migrations.py for why that
    # matters). IF NOT EXISTS keeps a re-run harmless.
    op.execute("ALTER TYPE explanation_kind ADD VALUE IF NOT EXISTS 'conversation'")


def downgrade() -> None:
    # PostgreSQL cannot drop a value from an enum. Rows of this kind would have
    # to be deleted and the type rebuilt; that is a deliberate operator action,
    # not something a downgrade should do silently.
    pass
