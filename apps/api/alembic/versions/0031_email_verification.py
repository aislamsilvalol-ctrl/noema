"""Email verification: when an account proved it owns its address, and the
one-time links that prove it.

`users.email_verified_at` stays NULL for every existing account -- nobody is
mass-verified, and nothing is gated on it yet (see
`NOEMA_REQUIRE_VERIFIED_EMAIL_FOR_AI`). The token table mirrors
`password_reset_tokens`: hashed, single-use, expiring.

Revision ID: 0031
Revises: 0030
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "email_verification_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("token_hash", name="uq_email_verification_tokens_token_hash"),
    )
    op.create_index(
        "ix_email_verification_tokens_user_id",
        "email_verification_tokens",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_email_verification_tokens_user_id", table_name="email_verification_tokens"
    )
    op.drop_table("email_verification_tokens")
    op.drop_column("users", "email_verified_at")
