"""Request and response schemas.

Response models are explicit rather than derived from ORM classes. That is what makes
"no schema in this app can carry a plaintext API key" a property you can read off the
file instead of a promise.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

Slug = Annotated[
    str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=200)
]
Title = Annotated[
    str, StringConstraints(min_length=1, max_length=200, strip_whitespace=True)
]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


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


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    display_name: str
    settings: dict[str, Any]
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


class ChatIn(BaseModel):
    notebook_id: uuid.UUID | None = None
    mode: TutorMode = "explain"
    messages: Annotated[list[ChatMessageIn], Field(min_length=1, max_length=100)]


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
