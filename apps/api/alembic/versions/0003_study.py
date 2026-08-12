"""Cards, FSRS schedules, the review log and derived mastery.

Revision ID: 0003
Revises: 0002

``reviews`` is the evidence log and is append-only. ``card_schedules`` and
``concept_mastery`` are projections that can be rebuilt from it — which is what
makes a bug in the scheduling or mastery model recoverable rather than permanent.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

CARD_TYPE = sa.Enum(
    "basic",
    "reverse",
    "cloze",
    "image",
    "concept",
    "definition",
    "code",
    name="card_type",
)
CARD_ORIGIN = sa.Enum("user", "ai", name="card_origin")
CARD_STATE = sa.Enum("new", "learning", "review", "relearning", name="card_state")


def _uuid_pk() -> sa.Column[Any]:
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True)


def _owner_fk() -> sa.Column[Any]:
    return sa.Column(
        "owner_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )


def _created() -> sa.Column[Any]:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )


def _updated() -> sa.Column[Any]:
    return sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "cards",
        _uuid_pk(),
        _owner_fk(),
        sa.Column(
            "notebook_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notebooks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("type", CARD_TYPE, nullable=False, server_default="basic"),
        sa.Column("front_md", sa.Text, nullable=False),
        sa.Column("back_md", sa.Text, nullable=False),
        sa.Column("cloze_map", postgresql.JSONB),
        sa.Column(
            "source_chunk_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("origin", CARD_ORIGIN, nullable=False, server_default="user"),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("suspended_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        _created(),
        _updated(),
    )
    op.create_index("ix_cards_owner_id", "cards", ["owner_id"])
    op.create_index("ix_cards_notebook_id", "cards", ["notebook_id"])
    op.create_index("ix_cards_concept_id", "cards", ["concept_id"])

    op.create_table(
        "card_schedules",
        _uuid_pk(),
        _owner_fk(),
        sa.Column(
            "card_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cards.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("stability", sa.Float, nullable=False, server_default="0"),
        sa.Column("difficulty", sa.Float, nullable=False, server_default="5"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_review_at", sa.DateTime(timezone=True)),
        sa.Column("reps", sa.Integer, nullable=False, server_default="0"),
        sa.Column("lapses", sa.Integer, nullable=False, server_default="0"),
        sa.Column("state", CARD_STATE, nullable=False, server_default="new"),
        _created(),
        _updated(),
    )
    op.create_index("ix_card_schedules_owner_id", "card_schedules", ["owner_id"])
    # The query behind every study session: what is due for this person, now.
    op.create_index(
        "ix_card_schedules_owner_due", "card_schedules", ["owner_id", "due_at"]
    )

    op.create_table(
        "reviews",
        _uuid_pk(),
        _owner_fk(),
        sa.Column(
            "card_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("state_before", postgresql.JSONB),
        sa.Column("state_after", postgresql.JSONB, nullable=False),
        sa.Column("elapsed_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("confidence", sa.Integer),
        sa.Column("scheduled_days", sa.Float, nullable=False, server_default="0"),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_reviews_owner_id", "reviews", ["owner_id"])
    op.create_index("ix_reviews_card_id", "reviews", ["card_id"])
    op.create_index("ix_reviews_concept_id", "reviews", ["concept_id"])
    op.create_index("ix_reviews_reviewed_at", "reviews", ["reviewed_at"])

    op.create_table(
        "concept_mastery",
        _uuid_pk(),
        _owner_fk(),
        sa.Column(
            "concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("concepts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mastery", sa.Float, nullable=False, server_default="0"),
        sa.Column("competence", sa.Float, nullable=False, server_default="0"),
        sa.Column("retrievability", sa.Float, nullable=False, server_default="0"),
        sa.Column("uncertainty", sa.Float, nullable=False, server_default="0"),
        sa.Column("calibration", sa.Float, nullable=False, server_default="0"),
        sa.Column("evidence_count", sa.Float, nullable=False, server_default="0"),
        sa.Column("last_evidence_at", sa.DateTime(timezone=True)),
        sa.Column("components", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("model_version", sa.Integer, nullable=False, server_default="1"),
        _created(),
        _updated(),
        sa.UniqueConstraint("owner_id", "concept_id", name="uq_concept_mastery_owner_id"),
    )
    op.create_index("ix_concept_mastery_owner_id", "concept_mastery", ["owner_id"])


def downgrade() -> None:
    op.drop_table("concept_mastery")
    op.drop_table("reviews")
    op.drop_table("card_schedules")
    op.drop_table("cards")
    CARD_STATE.drop(op.get_bind(), checkfirst=True)
    CARD_ORIGIN.drop(op.get_bind(), checkfirst=True)
    CARD_TYPE.drop(op.get_bind(), checkfirst=True)
