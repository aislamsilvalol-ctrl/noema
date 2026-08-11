"""SQLAlchemy models for Phase 1, plus the Phase 2 ingestion tables.

Schema rationale lives in ``docs/data-model.md``. Two rules enforced here:

* every user-owned table carries ``owner_id`` so the repository layer can scope
  queries without callers remembering to filter;
* credentials have no column, property or relationship that can surface plaintext.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from noema.core.config import get_settings
from noema.db.base import Base, IdMixin, OwnedEntity, TimestampMixin


def _enum_values(enum: type[StrEnum]) -> list[str]:
    return [member.value for member in enum]


class SourceKind(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    MD = "md"
    CSV = "csv"
    URL = "url"
    TRANSCRIPT = "transcript"
    PASTE = "paste"


class SourceStatus(StrEnum):
    PENDING = "pending"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    EXTRACTING = "extracting"
    READY = "ready"
    FAILED = "failed"


class User(IdMixin, Base, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(320), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    workspaces: Mapped[list[Workspace]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class Session(IdMixin, Base, TimestampMixin):
    """A refresh-token family. Rotation replaces rows; reuse revokes the family."""

    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), index=True, nullable=False
    )
    refresh_token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    ip_hash: Mapped[str | None] = mapped_column(String(64))


class Workspace(OwnedEntity, TimestampMixin):
    __tablename__ = "workspaces"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    owner: Mapped[User] = relationship(back_populates="workspaces")
    subjects: Mapped[list[Subject]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("owner_id", "slug"),)


class Subject(OwnedEntity, TimestampMixin):
    __tablename__ = "subjects"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    workspace: Mapped[Workspace] = relationship(back_populates="subjects")
    notebooks: Mapped[list[Notebook]] = relationship(
        back_populates="subject", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("workspace_id", "slug"),)


class Notebook(OwnedEntity, TimestampMixin):
    __tablename__ = "notebooks"

    subject_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    ai_provider_override: Mapped[str | None] = mapped_column(String(50))
    retrieval_settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    subject: Mapped[Subject] = relationship(back_populates="notebooks")
    notes: Mapped[list[Note]] = relationship(
        back_populates="notebook", cascade="all, delete-orphan"
    )
    sources: Mapped[list[Source]] = relationship(
        back_populates="notebook", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("subject_id", "slug"),)


class Note(OwnedEntity, TimestampMixin):
    __tablename__ = "notes"

    notebook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notebooks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    # Markdown is the source of truth; content_json holds the editor's tree so the
    # document survives a round-trip without lossy re-parsing.
    content_md: Mapped[str] = mapped_column(Text, default="", nullable=False)
    content_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    links: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    notebook: Mapped[Notebook] = relationship(back_populates="notes")


class Source(OwnedEntity, TimestampMixin):
    __tablename__ = "sources"

    notebook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notebooks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[SourceKind] = mapped_column(
        # values_callable is load-bearing: without it SQLAlchemy stores the member
        # *names* (MD) while the migration created the type with the *values* (md),
        # and every insert fails on a type the schema clearly declares.
        Enum(SourceKind, name="source_kind", values_callable=_enum_values),
        nullable=False,
    )
    original_filename: Mapped[str | None] = mapped_column(String(500))
    storage_key: Mapped[str | None] = mapped_column(String(500))
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    byte_size: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[SourceStatus] = mapped_column(
        Enum(SourceStatus, name="source_status", values_callable=_enum_values),
        default=SourceStatus.PENDING,
        nullable=False,
    )
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    notebook: Mapped[Notebook] = relationship(back_populates="sources")


class Chunk(OwnedEntity, TimestampMixin):
    """Embedded slice of a source.

    The vector width comes from ``NOEMA_EMBEDDING_DIM`` at import time, matching the
    migration. A deployment's embedding model is fixed at install; changing it means
    re-embedding, not altering the column, because mixing dimensions in one column is
    a failure mode we refuse rather than support.
    """

    __tablename__ = "chunks"

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True, nullable=False
    )
    notebook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notebooks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    heading_path: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, nullable=False
    )
    page_from: Mapped[int | None] = mapped_column(Integer)
    page_to: Mapped[int | None] = mapped_column(Integer)
    embedding_model: Mapped[str | None] = mapped_column(String(100))

    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(get_settings().noema_embedding_dim)
    )
    # Generated by Postgres so it can never drift from `content`. The 'simple'
    # configuration is deliberate: stemming an unknown mix of languages loses more
    # than it gains, and hybrid retrieval leans on the vector side for semantics.
    tsv: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', content)", persisted=True)
    )

    __table_args__ = (
        Index("ix_chunks_source_ordinal", "source_id", "ordinal", unique=True),
        # Declared here as well as created by the migration so `alembic check`
        # compares like with like and model drift stays detectable.
        Index(
            "ix_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
    )


class ProviderCredential(OwnedEntity, TimestampMixin):
    """A BYOK key. There is no plaintext column, and no API schema that can carry one."""

    __tablename__ = "provider_credentials"

    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    last4: Mapped[str] = mapped_column(String(8), nullable=False)

    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    wrapped_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    wrapped_key_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("owner_id", "provider", "label"),)


class AIUsage(OwnedEntity):
    """Per-call token accounting. BYOK users are spending their own money."""

    __tablename__ = "ai_usage"

    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    task: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_cents: Mapped[float] = mapped_column(default=0.0, nullable=False)
    succeeded: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
