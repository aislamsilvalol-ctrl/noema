"""V3 Professor Engine: journeys, student concept states, mastery events,
memory summaries, assessments; journey cards; usage by feature.

Revision ID: 0019
Revises: 0018
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def _owned(table: str) -> list[sa.Column[object]]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
    ]


def _timestamps() -> list[sa.Column[object]]:
    return [
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
    ]


def upgrade() -> None:
    # ── learning_journeys ──────────────────────────────────────────────────
    op.create_table(
        "learning_journeys",
        *_owned("learning_journeys"),
        sa.Column(
            "notebook_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notebooks.id", ondelete="SET NULL"),
        ),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("inferred_level", sa.String(32), nullable=False),
        sa.Column("desired_depth", sa.String(32), nullable=False),
        sa.Column("prerequisites", postgresql.JSONB(), nullable=False),
        sa.Column("plan", postgresql.JSONB(), nullable=False),
        sa.Column("current_module", sa.Integer(), nullable=False),
        sa.Column("current_lesson", sa.Integer(), nullable=False),
        sa.Column("current_concept", sa.String(200), nullable=False),
        sa.Column("profile", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("concepts_since_checkpoint", sa.Integer(), nullable=False),
        sa.Column("checkpoints", sa.Integer(), nullable=False),
        sa.Column("last_checkpoint_at", sa.DateTime(timezone=True)),
        sa.Column("pending_remediation", postgresql.JSONB(), nullable=False),
        sa.Column("last_active_at", sa.DateTime(timezone=True)),
        *_timestamps(),
    )
    op.create_index("ix_learning_journeys_owner_id", "learning_journeys", ["owner_id"])
    op.create_index(
        "ix_learning_journeys_notebook_id", "learning_journeys", ["notebook_id"]
    )
    op.create_index(
        "ix_learning_journeys_owner_active",
        "learning_journeys",
        ["owner_id", "last_active_at"],
    )

    # ── student_concept_states ─────────────────────────────────────────────
    op.create_table(
        "student_concept_states",
        *_owned("student_concept_states"),
        sa.Column(
            "journey_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learning_journeys.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("concepts.id", ondelete="SET NULL"),
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("normalized_name", sa.String(200), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("strong_evidence_count", sa.Integer(), nullable=False),
        sa.Column("correct_streak", sa.Integer(), nullable=False),
        sa.Column("wrong_streak", sa.Integer(), nullable=False),
        sa.Column("cards_count", sa.Integer(), nullable=False),
        sa.Column("misconceptions", postgresql.JSONB(), nullable=False),
        sa.Column("notes", postgresql.JSONB(), nullable=False),
        sa.Column("introduced_at", sa.DateTime(timezone=True)),
        sa.Column("last_evidence_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.UniqueConstraint(
            "journey_id",
            "normalized_name",
            name="uq_student_concept_states_journey_id",
        ),
    )
    op.create_index(
        "ix_student_concept_states_owner_id", "student_concept_states", ["owner_id"]
    )
    op.create_index(
        "ix_student_concept_states_journey_id",
        "student_concept_states",
        ["journey_id"],
    )

    # ── mastery_events ─────────────────────────────────────────────────────
    op.create_table(
        "mastery_events",
        *_owned("mastery_events"),
        sa.Column(
            "journey_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learning_journeys.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("concept_name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=False),
        sa.Column(
            "turn_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teaching_turns.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_mastery_events_owner_id", "mastery_events", ["owner_id"])
    op.create_index("ix_mastery_events_journey_id", "mastery_events", ["journey_id"])
    op.create_index("ix_mastery_events_created_at", "mastery_events", ["created_at"])

    # ── memory_summaries ───────────────────────────────────────────────────
    op.create_table(
        "memory_summaries",
        *_owned("memory_summaries"),
        sa.Column(
            "journey_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learning_journeys.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teaching_sessions.id", ondelete="SET NULL"),
        ),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("turn_from", sa.Integer(), nullable=False),
        sa.Column("turn_to", sa.Integer(), nullable=False),
        sa.Column("summary", postgresql.JSONB(), nullable=False),
        sa.Column("tokens_saved", sa.Integer(), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_memory_summaries_owner_id", "memory_summaries", ["owner_id"])
    op.create_index("ix_memory_summaries_journey_id", "memory_summaries", ["journey_id"])
    op.create_index("ix_memory_summaries_session_id", "memory_summaries", ["session_id"])
    op.create_index("ix_memory_summaries_created_at", "memory_summaries", ["created_at"])

    # ── assessments ────────────────────────────────────────────────────────
    op.create_table(
        "assessments",
        *_owned("assessments"),
        sa.Column(
            "journey_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learning_journeys.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teaching_sessions.id", ondelete="SET NULL"),
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("questions", postgresql.JSONB(), nullable=False),
        sa.Column("responses", postgresql.JSONB(), nullable=False),
        sa.Column("score", sa.Float()),
        sa.Column("results", postgresql.JSONB(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        *_timestamps(),
    )
    op.create_index("ix_assessments_owner_id", "assessments", ["owner_id"])
    op.create_index("ix_assessments_journey_id", "assessments", ["journey_id"])

    # ── teaching_sessions / teaching_turns ────────────────────────────────
    op.add_column(
        "teaching_sessions",
        sa.Column(
            "journey_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learning_journeys.id", ondelete="SET NULL"),
        ),
    )
    op.create_index(
        "ix_teaching_sessions_journey_id", "teaching_sessions", ["journey_id"]
    )
    op.add_column(
        "teaching_sessions",
        sa.Column("compacted_through", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "teaching_sessions",
        sa.Column("last_move", sa.String(24), nullable=False, server_default=""),
    )
    op.add_column(
        "teaching_sessions",
        sa.Column("wrong_streak", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "teaching_sessions",
        sa.Column("since_check", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("teaching_turns", sa.Column("blocks", postgresql.JSONB()))
    op.add_column(
        "teaching_turns",
        sa.Column("token_estimate", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("teaching_turns", sa.Column("archived_at", sa.DateTime(timezone=True)))

    # ── cards: a journey's cards have no notebook ─────────────────────────
    op.alter_column(
        "cards", "notebook_id", existing_type=postgresql.UUID(), nullable=True
    )
    op.add_column(
        "cards",
        sa.Column(
            "journey_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learning_journeys.id", ondelete="SET NULL"),
        ),
    )
    op.create_index("ix_cards_journey_id", "cards", ["journey_id"])
    op.add_column("cards", sa.Column("concept_name", sa.String(200)))

    # ── ai_usage: cache, feature, session ─────────────────────────────────
    op.add_column(
        "ai_usage",
        sa.Column("cached_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("ai_usage", sa.Column("feature", sa.String(50)))
    op.create_index("ix_ai_usage_feature", "ai_usage", ["feature"])
    op.add_column("ai_usage", sa.Column("session_id", postgresql.UUID(as_uuid=True)))
    op.create_index("ix_ai_usage_session_id", "ai_usage", ["session_id"])

    # Defaults were only needed to fill existing rows; the models set their own.
    for table, column in (
        ("teaching_sessions", "compacted_through"),
        ("teaching_sessions", "last_move"),
        ("teaching_sessions", "wrong_streak"),
        ("teaching_sessions", "since_check"),
        ("teaching_turns", "token_estimate"),
        ("ai_usage", "cached_tokens"),
    ):
        op.alter_column(table, column, server_default=None)


def downgrade() -> None:
    op.drop_index("ix_ai_usage_session_id", table_name="ai_usage")
    op.drop_column("ai_usage", "session_id")
    op.drop_index("ix_ai_usage_feature", table_name="ai_usage")
    op.drop_column("ai_usage", "feature")
    op.drop_column("ai_usage", "cached_tokens")

    op.drop_column("cards", "concept_name")
    op.drop_index("ix_cards_journey_id", table_name="cards")
    op.drop_column("cards", "journey_id")
    # Cards without a notebook cannot survive the old NOT NULL constraint.
    op.execute("DELETE FROM cards WHERE notebook_id IS NULL")
    op.alter_column(
        "cards", "notebook_id", existing_type=postgresql.UUID(), nullable=False
    )

    op.drop_column("teaching_turns", "archived_at")
    op.drop_column("teaching_turns", "token_estimate")
    op.drop_column("teaching_turns", "blocks")
    op.drop_column("teaching_sessions", "since_check")
    op.drop_column("teaching_sessions", "wrong_streak")
    op.drop_column("teaching_sessions", "last_move")
    op.drop_column("teaching_sessions", "compacted_through")
    op.drop_index("ix_teaching_sessions_journey_id", table_name="teaching_sessions")
    op.drop_column("teaching_sessions", "journey_id")

    op.drop_table("assessments")
    op.drop_table("memory_summaries")
    op.drop_table("mastery_events")
    op.drop_table("student_concept_states")
    op.drop_table("learning_journeys")
