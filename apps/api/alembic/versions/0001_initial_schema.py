"""Initial schema: identity, library hierarchy, ingestion tables, credentials, usage.

Revision ID: 0001
Create Date: Phase 1

The vector column and its HNSW index are created here with the dimension taken from
``NOEMA_EMBEDDING_DIM``, because a deployment's embedding model is fixed at install
time. Changing it requires a re-embed migration, not a column alter.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from noema.core.config import get_settings

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SOURCE_KIND = sa.Enum(
    "pdf", "docx", "txt", "md", "csv", "url", "transcript", "paste", name="source_kind"
)
SOURCE_STATUS = sa.Enum(
    "pending",
    "parsing",
    "chunking",
    "embedding",
    "extracting",
    "ready",
    "failed",
    name="source_status",
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # Factories rather than shared Column objects: a Column belongs to one table,
    # and Column.copy() is deprecated in SQLAlchemy 2.0.
    def uuid_pk() -> sa.Column[Any]:
        return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True)

    def created() -> sa.Column[Any]:
        return sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        )

    def updated() -> sa.Column[Any]:
        return sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        )

    def owner_fk() -> sa.Column[Any]:
        return sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        )

    op.create_table(
        "users",
        uuid_pk(),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("settings", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        created(),
        updated(),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "sessions",
        uuid_pk(),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("refresh_token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("user_agent", sa.String(400)),
        sa.Column("ip_hash", sa.String(64)),
        created(),
        updated(),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_family_id", "sessions", ["family_id"])

    def owned(name: str, *items: sa.schema.SchemaItem) -> None:
        op.create_table(
            name,
            uuid_pk(),
            owner_fk(),
            *items,
            created(),
            updated(),
        )
        op.create_index(f"ix_{name}_owner_id", name, ["owner_id"])

    owned(
        "workspaces",
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(200), nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("owner_id", "slug", name="uq_workspaces_owner_id"),
    )

    owned(
        "subjects",
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(200), nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_subjects_workspace_id"),
    )
    op.create_index("ix_subjects_workspace_id", "subjects", ["workspace_id"])

    owned(
        "notebooks",
        sa.Column(
            "subject_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subjects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("ai_provider_override", sa.String(50)),
        sa.Column(
            "retrieval_settings", postgresql.JSONB, nullable=False, server_default="{}"
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("subject_id", "slug", name="uq_notebooks_subject_id"),
    )
    op.create_index("ix_notebooks_subject_id", "notebooks", ["subject_id"])

    owned(
        "notes",
        sa.Column(
            "notebook_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notebooks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("content_md", sa.Text, nullable=False, server_default=""),
        sa.Column("content_json", postgresql.JSONB),
        sa.Column(
            "links", postgresql.ARRAY(sa.Text), nullable=False, server_default="{}"
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_notes_notebook_id", "notes", ["notebook_id"])

    owned(
        "sources",
        sa.Column(
            "notebook_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notebooks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", SOURCE_KIND, nullable=False),
        sa.Column("original_filename", sa.String(500)),
        sa.Column("storage_key", sa.String(500)),
        sa.Column("checksum_sha256", sa.String(64)),
        sa.Column("byte_size", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("page_count", sa.Integer),
        sa.Column("status", SOURCE_STATUS, nullable=False, server_default="pending"),
        sa.Column("error", postgresql.JSONB),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_sources_notebook_id", "sources", ["notebook_id"])
    op.create_index("ix_sources_checksum_sha256", "sources", ["checksum_sha256"])

    dim = get_settings().noema_embedding_dim
    owned(
        "chunks",
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "notebook_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notebooks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "heading_path", postgresql.ARRAY(sa.Text), nullable=False, server_default="{}"
        ),
        sa.Column("page_from", sa.Integer),
        sa.Column("page_to", sa.Integer),
        sa.Column("embedding_model", sa.String(100)),
    )
    op.create_index("ix_chunks_source_id", "chunks", ["source_id"])
    op.create_index(
        "ix_chunks_source_ordinal", "chunks", ["source_id", "ordinal"], unique=True
    )
    op.create_index("ix_chunks_notebook_id", "chunks", ["notebook_id"])

    op.execute(f"ALTER TABLE chunks ADD COLUMN embedding vector({dim})")
    op.execute(
        "ALTER TABLE chunks ADD COLUMN tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED"
    )
    # HNSW over cosine distance: hybrid retrieval fuses this with the tsvector index.
    op.create_index(
        "ix_chunks_embedding",
        "chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index("ix_chunks_tsv", "chunks", ["tsv"], postgresql_using="gin")

    owned(
        "provider_credentials",
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("last4", sa.String(8), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary, nullable=False),
        sa.Column("nonce", sa.LargeBinary, nullable=False),
        sa.Column("wrapped_key", sa.LargeBinary, nullable=False),
        sa.Column("wrapped_key_nonce", sa.LargeBinary, nullable=False),
        sa.Column("key_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("last_verified_at", sa.DateTime(timezone=True)),
        sa.Column("verification_error", sa.Text),
        sa.UniqueConstraint(
            "owner_id",
            "provider",
            "label",
            name="uq_provider_credentials_owner_id",
        ),
    )

    op.create_table(
        "ai_usage",
        uuid_pk(),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("task", sa.String(50), nullable=False),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_cents", sa.Float, nullable=False, server_default="0"),
        sa.Column("succeeded", sa.Boolean, nullable=False, server_default="true"),
        created(),
    )
    op.create_index("ix_ai_usage_owner_id", "ai_usage", ["owner_id"])
    op.create_index("ix_ai_usage_task", "ai_usage", ["task"])
    op.create_index("ix_ai_usage_created_at", "ai_usage", ["created_at"])


def downgrade() -> None:
    for table in (
        "ai_usage",
        "provider_credentials",
        "chunks",
        "sources",
        "notes",
        "notebooks",
        "subjects",
        "workspaces",
        "sessions",
        "users",
    ):
        op.drop_table(table)
    SOURCE_STATUS.drop(op.get_bind(), checkfirst=True)
    SOURCE_KIND.drop(op.get_bind(), checkfirst=True)
