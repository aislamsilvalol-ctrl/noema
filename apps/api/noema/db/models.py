"""SQLAlchemy models for Phase 1, plus the Phase 2 ingestion tables.

Schema rationale lives in ``docs/data-model.md``. Two rules enforced here:

* every user-owned table carries ``owner_id`` so the repository layer can scope
  queries without callers remembering to filter;
* credentials have no column, property or relationship that can surface plaintext.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Computed,
    Date,
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


class ConceptStatus(StrEnum):
    """A concept seen once with low confidence is noise, not knowledge.

    Candidates stay hidden until corroborated: a graph full of one-off extraction
    artefacts is worse than a small one, because the user stops trusting all of it.
    """

    CANDIDATE = "candidate"
    ACTIVE = "active"
    MERGED = "merged"
    REJECTED = "rejected"


class EdgeKind(StrEnum):
    PREREQUISITE_OF = "prerequisite_of"
    PART_OF = "part_of"
    RELATED_TO = "related_to"
    CONTRASTS_WITH = "contrasts_with"


class EdgeOrigin(StrEnum):
    EXTRACTED = "extracted"
    INFERRED = "inferred"
    USER = "user"


class Concept(OwnedEntity, TimestampMixin):
    """A thing the learner is trying to understand.

    Canonical at workspace scope: "gradient descent" met in two notebooks of the
    same workspace is one concept, because mastery of it is one fact about the
    person, not two.
    """

    __tablename__ = "concepts"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    definition: Mapped[str | None] = mapped_column(Text)
    difficulty_prior: Mapped[float] = mapped_column(default=0.5, nullable=False)
    status: Mapped[ConceptStatus] = mapped_column(
        Enum(ConceptStatus, name="concept_status", values_callable=_enum_values),
        default=ConceptStatus.CANDIDATE,
        nullable=False,
    )
    #: Provenance. An extracted concept with no chunks behind it is a hallucination,
    #: and the graph refuses to show one.
    source_chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), default=list, nullable=False
    )
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="SET NULL")
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(get_settings().noema_embedding_dim)
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "normalized_name"),
        # Declared here as well as created by the migration, so `alembic check`
        # compares like with like and real drift stays detectable.
        Index(
            "ix_concepts_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class ConceptEdge(OwnedEntity, TimestampMixin):
    """A typed, weighted relation between two concepts."""

    __tablename__ = "concept_edges"

    src_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    dst_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[EdgeKind] = mapped_column(
        Enum(EdgeKind, name="edge_kind", values_callable=_enum_values), nullable=False
    )
    weight: Mapped[float] = mapped_column(default=0.5, nullable=False)
    origin: Mapped[EdgeOrigin] = mapped_column(
        Enum(EdgeOrigin, name="edge_origin", values_callable=_enum_values),
        default=EdgeOrigin.EXTRACTED,
        nullable=False,
    )

    __table_args__ = (UniqueConstraint("src_id", "dst_id", "kind"),)


class CardType(StrEnum):
    BASIC = "basic"
    REVERSE = "reverse"
    CLOZE = "cloze"
    IMAGE = "image"
    CONCEPT = "concept"
    DEFINITION = "definition"
    CODE = "code"


class CardOrigin(StrEnum):
    USER = "user"
    AI = "ai"


class CardState(StrEnum):
    NEW = "new"
    LEARNING = "learning"
    REVIEW = "review"
    RELEARNING = "relearning"


class Grader(StrEnum):
    DETERMINISTIC = "deterministic"
    AI = "ai"
    SELF = "self"


class Card(OwnedEntity, TimestampMixin):
    """A prompt and its answer.

    AI-generated cards are inert until ``approved_at`` is set. A card the learner
    never read before it entered their rotation is a claim they will memorise
    without ever having agreed to it.
    """

    __tablename__ = "cards"

    notebook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notebooks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    concept_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="SET NULL"), index=True
    )
    type: Mapped[CardType] = mapped_column(
        Enum(CardType, name="card_type", values_callable=_enum_values),
        default=CardType.BASIC,
        nullable=False,
    )
    front_md: Mapped[str] = mapped_column(Text, nullable=False)
    back_md: Mapped[str] = mapped_column(Text, nullable=False)
    #: Storage key for an image attached to the front — a diagram or screenshot
    #: the question refers to. Only ``CardType.IMAGE`` cards set this.
    front_image_key: Mapped[str | None] = mapped_column(String(500))
    cloze_map: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    source_chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), default=list, nullable=False
    )
    origin: Mapped[CardOrigin] = mapped_column(
        Enum(CardOrigin, name="card_origin", values_callable=_enum_values),
        default=CardOrigin.USER,
        nullable=False,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def has_image(self) -> bool:
        return self.front_image_key is not None


class CardSchedule(OwnedEntity, TimestampMixin):
    """FSRS state for one card — a projection, rebuildable from ``reviews``."""

    __tablename__ = "card_schedules"

    card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cards.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    stability: Mapped[float] = mapped_column(default=0.0, nullable=False)
    difficulty: Mapped[float] = mapped_column(default=5.0, nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lapses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    state: Mapped[CardState] = mapped_column(
        Enum(CardState, name="card_state", values_callable=_enum_values),
        default=CardState.NEW,
        nullable=False,
    )

    __table_args__ = (Index("ix_card_schedules_owner_due", "owner_id", "due_at"),)


class Review(OwnedEntity):
    """One graded recall attempt. Append-only: this is the evidence log.

    Everything derived — schedules, mastery — can be rebuilt from these rows, which
    is what makes a bug in the scheduling or mastery model recoverable rather than
    permanent.
    """

    __tablename__ = "reviews"

    card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cards.id", ondelete="CASCADE"), index=True, nullable=False
    )
    concept_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="SET NULL"), index=True
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    state_before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    state_after: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence: Mapped[int | None] = mapped_column(Integer)
    scheduled_days: Mapped[float] = mapped_column(default=0.0, nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class ConceptMastery(OwnedEntity, TimestampMixin):
    """Derived mastery for one concept.

    A projection, versioned by the model that produced it so a formula change can be
    rebuilt and compared rather than silently replacing the old numbers.
    """

    __tablename__ = "concept_mastery"

    concept_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False
    )
    mastery: Mapped[float] = mapped_column(default=0.0, nullable=False)
    competence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    retrievability: Mapped[float] = mapped_column(default=0.0, nullable=False)
    uncertainty: Mapped[float] = mapped_column(default=0.0, nullable=False)
    calibration: Mapped[float] = mapped_column(default=0.0, nullable=False)
    evidence_count: Mapped[float] = mapped_column(default=0.0, nullable=False)
    last_evidence_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: The term-by-term breakdown, so the UI can explain the number rather than
    #: assert it. A score a learner cannot interrogate is one they will not trust.
    components: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    model_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (UniqueConstraint("owner_id", "concept_id"),)


class QuestionType(StrEnum):
    MCQ = "mcq"
    TRUE_FALSE = "true_false"
    OPEN = "open"
    FILL_BLANK = "fill_blank"
    MATCHING = "matching"
    ORDERING = "ordering"
    CODE = "code"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    EXPERT = "expert"


class Question(OwnedEntity, TimestampMixin):
    """A question with a gradeable answer.

    Unlike a card, a question carries a real difficulty — which is what the mastery
    model needs: card reviews are self-graded and mid-difficulty by construction, so
    they cannot distinguish someone who finds a topic easy from someone who is only
    ever asked easy things about it.
    """

    __tablename__ = "questions"

    notebook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notebooks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    concept_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="SET NULL"), index=True
    )
    type: Mapped[QuestionType] = mapped_column(
        Enum(QuestionType, name="question_type", values_callable=_enum_values),
        nullable=False,
    )
    difficulty: Mapped[Difficulty] = mapped_column(
        Enum(Difficulty, name="question_difficulty", values_callable=_enum_values),
        default=Difficulty.MEDIUM,
        nullable=False,
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    #: Type-specific: options and the correct index for MCQ, the accepted answers
    #: for fill-in-the-blank, the pairs for matching, the ordered items for ordering.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    #: What a good open answer must contain. Grading against a rubric is why an open
    #: answer can be scored on understanding rather than on wording.
    rubric: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    source_chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), default=list, nullable=False
    )
    origin: Mapped[CardOrigin] = mapped_column(
        Enum(CardOrigin, name="card_origin", values_callable=_enum_values),
        default=CardOrigin.AI,
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Answer(OwnedEntity):
    """One graded attempt at a question. Append-only, like reviews."""

    __tablename__ = "answers"

    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    concept_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="SET NULL"), index=True
    )
    response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    #: Partial credit, so an answer that gets the idea but misses a condition is not
    #: scored the same as one that is simply wrong.
    score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    confidence: Mapped[int | None] = mapped_column(Integer)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    grader: Mapped[Grader] = mapped_column(
        Enum(Grader, name="grader", values_callable=_enum_values),
        default=Grader.DETERMINISTIC,
        nullable=False,
    )
    feedback: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class Mistake(OwnedEntity, TimestampMixin):
    """A wrong answer worth returning to.

    A wrong answer given with high confidence is the failure mode plain spaced
    repetition never catches: the learner has a coherent wrong model and no reason
    to flag it for review.
    """

    __tablename__ = "mistakes"

    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    answer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("answers.id", ondelete="CASCADE"), nullable=False
    )
    concept_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="SET NULL"), index=True
    )
    confidence: Mapped[int | None] = mapped_column(Integer)
    is_misconception: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StudySession(OwnedEntity, TimestampMixin):
    """A planned session, stored with what the engine decided and what happened.

    The plan is kept verbatim so a scheduler change can be replayed against real
    history and compared, rather than argued about. Every constant in
    ``SchedulerSettings`` is a hypothesis until this table has enough rows to test
    it — see ``docs/learning-engine.md`` §8.
    """

    __tablename__ = "study_sessions"

    planned_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_seconds: Mapped[float] = mapped_column(default=0.0, nullable=False)
    #: What actually elapsed, once the session is completed. The gap between this
    #: and the estimate is the planner's calibration.
    actual_seconds: Mapped[float | None] = mapped_column()
    rationale: Mapped[str] = mapped_column(Text, default="", nullable=False)
    plan: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    items_planned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Exam(OwnedEntity, TimestampMixin):
    """A timed run at a fixed set of questions, graded only at the end.

    Its own table rather than a `StudySession` with a flag: the planner's
    calibration is computed from those rows, and an exam is not a planned session
    — counting it as one would quietly corrupt the number that says whether the
    planner estimates time well.

    The questions are fixed at creation. An exam whose contents can change while
    it is being taken measures nothing.
    """

    __tablename__ = "exams"

    notebook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notebooks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    question_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Fraction of the available marks, not a percentage: the UI decides how to
    #: say it.
    score: Mapped[float | None] = mapped_column()
    #: Whether it was handed in after time. Recorded rather than refused — losing
    #: a learner's work to a clock is a worse failure than an untimed result.
    overtime: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: Per-concept outcome, so the result says what to study rather than a mark.
    results: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class ExplanationKind(StrEnum):
    #: The learner wrote an explanation unprompted.
    FEYNMAN = "feynman"
    #: The learner was questioned until they said it themselves.
    SOCRATIC = "socratic"


class Explanation(OwnedEntity, TimestampMixin):
    """A learner explaining a concept in their own words, and what was missing.

    Kept because it is evidence: producing an explanation unaided is a harder
    retrieval than recognising an option, and the mastery engine weights it as
    such. Kept verbatim too, because the useful thing months later is not the
    score — it is reading what you used to think.
    """

    __tablename__ = "explanations"

    concept_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: How the words were produced. Both are the learner demonstrating understanding
    #: in prose and both count as evidence, but reaching an idea under questioning
    #: is not the same act as producing it cold, and the record should say which.
    kind: Mapped[ExplanationKind] = mapped_column(
        Enum(ExplanationKind, name="explanation_kind", values_callable=_enum_values),
        default=ExplanationKind.FEYNMAN,
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    grader: Mapped[Grader] = mapped_column(
        Enum(Grader, name="grader", values_callable=_enum_values),
        default=Grader.AI,
        nullable=False,
    )
    #: The dialogue, for a Socratic session. Empty for a written explanation.
    transcript: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    #: gaps, oversimplifications, assumed prerequisites, contradictions, next step.
    findings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    explained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class Goal(OwnedEntity, TimestampMixin):
    """Something to know by a date.

    The path is not stored. It is derived from current mastery and the graph, and
    a plan pinned at creation would describe a learner who no longer exists by
    Wednesday — the point of the deadline is that the plan moves under it.
    """

    __tablename__ = "goals"

    notebook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notebooks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    due_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    target_mastery: Mapped[float] = mapped_column(default=80.0, nullable=False)
    #: What the learner says they can give it. The honest verdict depends on this
    #: more than on anything the engine knows.
    minutes_per_day: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    achieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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


class ApiToken(OwnedEntity, TimestampMixin):
    """A credential for the public REST API. There is no plaintext column here
    either — same rule as `ProviderCredential`, for the same reason: a database
    leak must not be a token leak. The plaintext is shown to its owner exactly
    once, at creation.
    """

    __tablename__ = "api_tokens"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    #: "read", "write", or both. "write" implies "read" — see
    #: `noema.api.v1.deps.get_current_user`, the one place that checks this.
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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


class ModelTier(StrEnum):
    """A cost tier, not a task. ``TaskClass`` (``noema/providers/base.py``) says what
    a call is for; a tier says how much the platform is willing to spend on it.
    A caller picks a tier the way it already picks a task class — the two compose,
    they don't replace each other."""

    ECONOMY = "economy"
    STANDARD = "standard"
    PREMIUM = "premium"


class ModelTierConfig(Base, TimestampMixin):
    """Which model backs each cost tier, and what it costs.

    One row per tier, platform-wide — not owned by a user, the way pricing on a
    menu isn't owned by a diner. ``tier`` is the primary key on purpose: there is
    exactly one active model per tier, and looking one up should never need to
    reason about "which row." Changing a tier's model or price is an update to
    the existing row, never an insert.

    Cost columns are seeded at ``0.0`` deliberately rather than with a guessed
    figure — provider pricing moves independently of this codebase, and a wrong
    number silently baked in reads as real cost accounting when it is fiction.
    Whoever operates a deployment has to set real prices before the numbers this
    feeds (usage accounting, the economics simulator) mean anything.
    """

    __tablename__ = "model_tier_configs"

    tier: Mapped[ModelTier] = mapped_column(
        Enum(ModelTier, name="model_tier", values_callable=_enum_values),
        primary_key=True,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    input_cost_per_million_usd: Mapped[float] = mapped_column(default=0.0, nullable=False)
    cached_input_cost_per_million_usd: Mapped[float] = mapped_column(
        default=0.0, nullable=False
    )
    output_cost_per_million_usd: Mapped[float] = mapped_column(
        default=0.0, nullable=False
    )
