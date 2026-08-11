"""Concepts and typed edges between them.

Revision ID: 0002
Revises: 0001

Concepts are canonical at workspace scope, so the unique index is on
``(workspace_id, normalized_name)`` — the same idea met in two notebooks is one
concept, because mastery of it is one fact about the person.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from noema.core.config import get_settings

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

CONCEPT_STATUS = sa.Enum(
    "candidate", "active", "merged", "rejected", name="concept_status"
)
EDGE_KIND = sa.Enum(
    "prerequisite_of", "part_of", "related_to", "contrasts_with", name="edge_kind"
)
EDGE_ORIGIN = sa.Enum("extracted", "inferred", "user", name="edge_origin")


def upgrade() -> None:
    def uuid_pk() -> sa.Column[Any]:
        return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True)

    def owner_fk() -> sa.Column[Any]:
        return sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        )

    def timestamps() -> tuple[sa.Column[Any], sa.Column[Any]]:
        return (
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
        )

    op.create_table(
        "concepts",
        uuid_pk(),
        owner_fk(),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("normalized_name", sa.String(200), nullable=False),
        sa.Column(
            "aliases", postgresql.ARRAY(sa.Text), nullable=False, server_default="{}"
        ),
        sa.Column("definition", sa.Text),
        sa.Column("difficulty_prior", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("status", CONCEPT_STATUS, nullable=False, server_default="candidate"),
        sa.Column(
            "source_chunk_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "merged_into_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("concepts.id", ondelete="SET NULL"),
        ),
        *timestamps(),
        sa.UniqueConstraint(
            "workspace_id", "normalized_name", name="uq_concepts_workspace_id"
        ),
    )
    op.create_index("ix_concepts_owner_id", "concepts", ["owner_id"])
    op.create_index("ix_concepts_workspace_id", "concepts", ["workspace_id"])
    op.create_index("ix_concepts_normalized_name", "concepts", ["normalized_name"])

    # Concepts carry an embedding so near-duplicates can be found by meaning rather
    # than by string edit distance — "back-propagation" and "backprop" are the same
    # idea and share almost no characters.
    dim = get_settings().noema_embedding_dim
    op.execute(f"ALTER TABLE concepts ADD COLUMN embedding vector({dim})")
    op.create_index(
        "ix_concepts_embedding",
        "concepts",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "concept_edges",
        uuid_pk(),
        owner_fk(),
        sa.Column(
            "src_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("concepts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dst_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("concepts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", EDGE_KIND, nullable=False),
        sa.Column("weight", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("origin", EDGE_ORIGIN, nullable=False, server_default="extracted"),
        *timestamps(),
        sa.UniqueConstraint("src_id", "dst_id", "kind", name="uq_concept_edges_src_id"),
    )
    op.create_index("ix_concept_edges_owner_id", "concept_edges", ["owner_id"])
    op.create_index("ix_concept_edges_src_id", "concept_edges", ["src_id"])
    op.create_index("ix_concept_edges_dst_id", "concept_edges", ["dst_id"])


def downgrade() -> None:
    op.drop_table("concept_edges")
    op.drop_table("concepts")
    EDGE_ORIGIN.drop(op.get_bind(), checkfirst=True)
    EDGE_KIND.drop(op.get_bind(), checkfirst=True)
    CONCEPT_STATUS.drop(op.get_bind(), checkfirst=True)
