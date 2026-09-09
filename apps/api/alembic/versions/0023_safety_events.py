"""Safety events (Noema Guard).

One row per above-SAFE Noema Guard classification -- never the message
that triggered it, just the category, risk level, and action taken. See
`noema.db.models.SafetyEvent`.

Revision ID: 0023
Revises: 0022
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

_RISK_LEVEL_ENUM = sa.Enum(
    "safe", "sensitive", "restricted", "high_risk", "blocked", name="risk_level"
)
_SAFETY_ACTION_ENUM = sa.Enum(
    "allow",
    "allow_with_context",
    "educational_safe_response",
    "redirect",
    "partial_refusal",
    "block",
    name="safety_action",
)


def upgrade() -> None:
    # No explicit .create() here -- op.create_table's own DDL creates both enum
    # types as part of creating the table, same reasoning as 0012's model_tier
    # enum (see that migration's comment; calling .create() first double-creates
    # it and fails "type already exists").
    op.create_table(
        "safety_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("risk_level", _RISK_LEVEL_ENUM, nullable=False),
        sa.Column("action", _SAFETY_ACTION_ENUM, nullable=False),
        sa.Column("escalated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_safety_events_user_id", "safety_events", ["user_id"])
    op.create_index("ix_safety_events_risk_level", "safety_events", ["risk_level"])
    op.create_index("ix_safety_events_created_at", "safety_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("safety_events")
    _SAFETY_ACTION_ENUM.drop(op.get_bind(), checkfirst=True)
    _RISK_LEVEL_ENUM.drop(op.get_bind(), checkfirst=True)
