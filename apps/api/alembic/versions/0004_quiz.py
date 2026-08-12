"""Questions, graded answers and the mistake bank.

Revision ID: 0004
Revises: 0003

Questions carry a real difficulty, which is what the mastery model has been missing:
card reviews are self-graded and mid-difficulty by construction, so they cannot tell
someone who finds a topic easy from someone who is only ever asked easy things.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

QUESTION_TYPE = sa.Enum(
    "mcq",
    "true_false",
    "open",
    "fill_blank",
    "matching",
    "ordering",
    "code",
    name="question_type",
)
QUESTION_DIFFICULTY = sa.Enum(
    "easy", "medium", "hard", "expert", name="question_difficulty"
)
GRADER = sa.Enum("deterministic", "ai", "self", name="grader")

#: Created in 0003. Referencing it again must not try to create it a second time.
CARD_ORIGIN = postgresql.ENUM("user", "ai", name="card_origin", create_type=False)


def _uuid_pk() -> sa.Column[Any]:
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True)


def _owner_fk() -> sa.Column[Any]:
    return sa.Column(
        "owner_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )


def _concept_fk() -> sa.Column[Any]:
    return sa.Column(
        "concept_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("concepts.id", ondelete="SET NULL"),
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
        "questions",
        _uuid_pk(),
        _owner_fk(),
        sa.Column(
            "notebook_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notebooks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        _concept_fk(),
        sa.Column("type", QUESTION_TYPE, nullable=False),
        sa.Column(
            "difficulty", QUESTION_DIFFICULTY, nullable=False, server_default="medium"
        ),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("rubric", postgresql.JSONB),
        sa.Column(
            "source_chunk_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("origin", CARD_ORIGIN, nullable=False, server_default="ai"),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        _created(),
        _updated(),
    )
    op.create_index("ix_questions_owner_id", "questions", ["owner_id"])
    op.create_index("ix_questions_notebook_id", "questions", ["notebook_id"])
    op.create_index("ix_questions_concept_id", "questions", ["concept_id"])

    op.create_table(
        "answers",
        _uuid_pk(),
        _owner_fk(),
        sa.Column(
            "question_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        _concept_fk(),
        sa.Column("response", postgresql.JSONB, nullable=False),
        sa.Column("is_correct", sa.Boolean, nullable=False),
        sa.Column("score", sa.Float, nullable=False, server_default="0"),
        sa.Column("confidence", sa.Integer),
        sa.Column("elapsed_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("grader", GRADER, nullable=False, server_default="deterministic"),
        sa.Column("feedback", postgresql.JSONB),
        sa.Column(
            "answered_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_answers_owner_id", "answers", ["owner_id"])
    op.create_index("ix_answers_question_id", "answers", ["question_id"])
    op.create_index("ix_answers_concept_id", "answers", ["concept_id"])
    op.create_index("ix_answers_answered_at", "answers", ["answered_at"])

    op.create_table(
        "mistakes",
        _uuid_pk(),
        _owner_fk(),
        sa.Column(
            "question_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "answer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("answers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        _concept_fk(),
        sa.Column("confidence", sa.Integer),
        sa.Column("is_misconception", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("summary", sa.Text),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        _created(),
        _updated(),
    )
    op.create_index("ix_mistakes_owner_id", "mistakes", ["owner_id"])
    op.create_index("ix_mistakes_question_id", "mistakes", ["question_id"])
    op.create_index("ix_mistakes_concept_id", "mistakes", ["concept_id"])


def downgrade() -> None:
    op.drop_table("mistakes")
    op.drop_table("answers")
    op.drop_table("questions")
    GRADER.drop(op.get_bind(), checkfirst=True)
    QUESTION_DIFFICULTY.drop(op.get_bind(), checkfirst=True)
    QUESTION_TYPE.drop(op.get_bind(), checkfirst=True)
