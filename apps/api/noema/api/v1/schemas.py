"""Request and response schemas.

Response models are explicit rather than derived from ORM classes. That is what makes
"no schema in this app can carry a plaintext API key" a property you can read off the
file instead of a promise.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    model_validator,
)

from noema.db.models import Plan

Slug = Annotated[
    str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=200)
]
Title = Annotated[
    str, StringConstraints(min_length=1, max_length=200, strip_whitespace=True)
]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def reject_explicit_null(model: BaseModel, *fields: str) -> None:
    """Raise if any of ``fields`` was sent as JSON ``null`` rather than omitted.

    A PATCH schema types every field ``X | None = None`` so it can be left out
    of the request — ``exclude_unset=True`` at the call site is what actually
    tells "omitted" apart from "sent as null". Some of those fields back a
    ``NOT NULL`` column; sending them as null explicitly reaches the database
    as an unhandled ``IntegrityError`` (a raw 500) instead of a clean 422
    unless it is rejected here first.
    """
    for field in fields:
        if field in model.model_fields_set and getattr(model, field) is None:
            raise ValueError(f"{field} cannot be cleared to null")


# ── Auth ──────────────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: EmailStr
    # 12 characters, no composition rules. Length beats forced symbols, and
    # arbitrary rules push people toward predictable substitutions.
    password: Annotated[str, StringConstraints(min_length=12, max_length=200)]
    display_name: Annotated[str, StringConstraints(min_length=1, max_length=120)]


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    # Same rule as RegisterRequest's own password field -- one place would
    # be better, but the two models don't otherwise share a base and this is
    # a two-line duplication, not a real inconsistency risk.
    new_password: Annotated[str, StringConstraints(min_length=12, max_length=200)]


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    display_name: str
    settings: dict[str, Any]
    #: A user's own plan is not sensitive to expose to themselves -- needed so
    #: the billing UI can show "you're on Pro" vs. offer to subscribe, without
    #: a second round trip to an admin-only endpoint the caller cannot reach.
    plan: Plan
    created_at: datetime


class SessionOut(BaseModel):
    user: UserOut
    csrf_token: str
    expires_at: datetime


# ── Hierarchy ─────────────────────────────────────────────────────────────────


class WorkspaceCreate(BaseModel):
    title: Title
    slug: Slug | None = None


class WorkspaceOut(ORMModel):
    id: uuid.UUID
    title: str
    slug: str
    position: int
    created_at: datetime


class SubjectCreate(BaseModel):
    workspace_id: uuid.UUID
    title: Title
    slug: Slug | None = None


class SubjectOut(ORMModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    slug: str
    position: int
    created_at: datetime


class NotebookCreate(BaseModel):
    subject_id: uuid.UUID
    title: Title
    slug: Slug | None = None
    description: str | None = None


class NotebookUpdate(BaseModel):
    title: Title | None = None
    description: str | None = None
    ai_provider_override: str | None = None
    retrieval_settings: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _no_null_required_fields(self) -> NotebookUpdate:
        reject_explicit_null(self, "title", "retrieval_settings")
        return self


class NotebookOut(ORMModel):
    id: uuid.UUID
    subject_id: uuid.UUID
    title: str
    slug: str
    description: str | None
    ai_provider_override: str | None
    retrieval_settings: dict[str, Any]
    created_at: datetime
    updated_at: datetime


# ── Notes ─────────────────────────────────────────────────────────────────────


class NoteCreate(BaseModel):
    notebook_id: uuid.UUID
    title: Annotated[str, StringConstraints(min_length=1, max_length=300)]
    content_md: str = ""
    content_json: dict[str, Any] | None = None


class NoteUpdate(BaseModel):
    title: Annotated[str, StringConstraints(min_length=1, max_length=300)] | None = None
    content_md: str | None = None
    content_json: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _no_null_required_fields(self) -> NoteUpdate:
        reject_explicit_null(self, "title", "content_md")
        return self


class NoteOut(ORMModel):
    id: uuid.UUID
    notebook_id: uuid.UUID
    title: str
    content_md: str
    content_json: dict[str, Any] | None
    links: list[str]
    created_at: datetime
    updated_at: datetime


# ── AI ────────────────────────────────────────────────────────────────────────

TutorMode = Literal["explain", "socratic", "examiner", "study_partner", "feynman"]


class ChatMessageIn(BaseModel):
    role: Literal["user", "assistant"]
    content: Annotated[str, StringConstraints(min_length=1, max_length=32_000)]


class LearningEventIn(BaseModel):
    """What the interface reports happened since the last turn.

    A quiz option chosen (with the engine's verdict), an open check answered
    (the answer is the message itself), an assessment handed in. The router
    reads these as facts; the model never sees them as instructions.
    """

    kind: Literal["quiz", "check", "flashcard", "assessment"]
    concept: Annotated[str, StringConstraints(max_length=200)] = ""
    correct: bool | None = None
    score: Annotated[float, Field(ge=0.0, le=1.0)] | None = None
    question: Annotated[str, StringConstraints(max_length=600)] = ""
    chosen: Annotated[str, StringConstraints(max_length=300)] = ""
    assessment_id: uuid.UUID | None = None


class ChatIn(BaseModel):
    notebook_id: uuid.UUID | None = None
    #: The teaching session this message continues. Absent on a first message;
    #: the Professor creates one and returns its id in a `session` event so the
    #: client can send it back — and so tomorrow's message finds today's lesson.
    session_id: uuid.UUID | None = None
    mode: TutorMode = "explain"
    #: The conversation as the client has it. Since V3 the Professor builds its
    #: own context from the stored turns and reads only the last message here;
    #: `/ai/chat` still uses the whole list.
    messages: Annotated[list[ChatMessageIn], Field(min_length=1, max_length=100)]
    # Answering from the notebook is the default; turning it off is the explicit,
    # labelled choice offered after a refusal, never a silent fallback.
    grounded: bool = True
    learning_event: LearningEventIn | None = None


class TeachingTurnOut(BaseModel):
    role: Literal["learner", "noema"]
    content: str
    intent: str
    created_at: datetime
    #: The validated learning blocks this reply carried (quiz, layers …), so a
    #: resumed lesson redraws them as UI. Private fields (a check's rubric)
    #: are stripped before this leaves the server.
    blocks: list[dict[str, Any]] | None = None


class TeachingSessionOut(BaseModel):
    """A lesson as the client resumes it: where it is, and what was said.

    The professor's structured decisions and metadata stay server-side; this is
    the learner-facing shape — enough to show "where we stopped" and to replay
    the transcript, nothing the interface would have to hide.
    """

    id: uuid.UUID
    notebook_id: uuid.UUID | None
    #: The journey this sitting belongs to (V3); null for pre-V3 sessions.
    journey_id: uuid.UUID | None = None
    learning_goal: str
    subject: str
    current_topic: str
    current_concept: str
    plan: list[dict[str, Any]]
    turn_count: int
    last_turn_at: datetime | None
    ended_at: datetime | None
    turns: list[TeachingTurnOut]


class ProviderOut(BaseModel):
    name: str
    configured: bool
    capabilities: dict[str, Any]
    is_default: bool


class CredentialCreate(BaseModel):
    """Write-only. There is deliberately no response model containing ``api_key``."""

    provider: Annotated[str, StringConstraints(min_length=2, max_length=50)]
    label: Annotated[str, StringConstraints(min_length=1, max_length=120)] = "default"
    api_key: Annotated[str, StringConstraints(min_length=8, max_length=500)]


class CredentialOut(BaseModel):
    id: uuid.UUID
    provider: str
    label: str
    last4: str
    created_at: datetime
    last_used_at: datetime | None
    last_verified_at: datetime | None
    verification_error: str | None


class UsageOut(BaseModel):
    task: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    cost_cents: float


# ── Pagination ────────────────────────────────────────────────────────────────


class Page[T](BaseModel):
    items: list[T]
    next_cursor: uuid.UUID | None = None
