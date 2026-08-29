"""The AI provider contract.

Every model call in NOEMA goes through this interface and through the gateway that
wraps it. Feature code never imports a vendor SDK — see ``docs/ai-providers.md``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, Protocol, runtime_checkable

__all__ = [
    "AIProvider",
    "Capabilities",
    "ChatRequest",
    "ChatResponse",
    "EmbedRequest",
    "EmbedResponse",
    "Message",
    "ProviderError",
    "Role",
    "StreamEvent",
    "StructuredRequest",
    "TaskClass",
    "Usage",
]


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class TaskClass(StrEnum):
    """What a call is *for*. Users route models per task, not per call site."""

    TUTOR_CHAT = "tutor.chat"
    EXTRACT_CONCEPTS = "extract.concepts"
    GENERATE_CARDS = "generate.cards"
    GENERATE_QUESTIONS = "generate.questions"
    GRADE_OPEN_ANSWER = "grade.open_answer"
    SUMMARIZE = "summarize"
    EMBED = "embed"
    CLASSIFY_INTENT = "classify.intent"


StructuredMode = Literal["native", "tool_call", "prompted", "none"]


@dataclass(frozen=True, slots=True)
class Capabilities:
    """What a provider can actually do, so callers negotiate instead of guessing."""

    chat: bool = False
    streaming: bool = False
    embeddings: bool = False
    structured_output: StructuredMode = "none"
    vision: bool = False
    max_context: int = 8192
    max_output: int = 4096


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_cents: float = 0.0


@dataclass(frozen=True, slots=True)
class ChatRequest:
    messages: Sequence[Message]
    task: TaskClass
    model: str | None = None
    temperature: float = 0.2
    max_tokens: int | None = None
    stop: Sequence[str] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ChatResponse:
    content: str
    model: str
    usage: Usage
    finish_reason: Literal["stop", "length", "content_filter", "error"] = "stop"


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """A streamed chunk. ``usage`` is present only on the terminal event."""

    delta: str = ""
    done: bool = False
    usage: Usage | None = None


@dataclass(frozen=True, slots=True)
class EmbedRequest:
    texts: Sequence[str]
    model: str | None = None


@dataclass(frozen=True, slots=True)
class EmbedResponse:
    vectors: Sequence[Sequence[float]]
    model: str
    dimensions: int
    usage: Usage


@dataclass(frozen=True, slots=True)
class StructuredRequest:
    """A call whose output must validate against ``json_schema``.

    Providers without native schema support fall back to a tool-call shim, then to
    prompted JSON with retry. Whatever the path, nothing is persisted before the
    result validates.
    """

    messages: Sequence[Message]
    json_schema: dict[str, Any]
    task: TaskClass
    model: str | None = None
    max_retries: int = 2


@dataclass(frozen=True, slots=True)
class HealthReport:
    healthy: bool
    latency_ms: float | None = None
    detail: str | None = None


class ProviderError(Exception):
    """Base class for provider failures.

    ``retryable`` drives the gateway's backoff: transport errors and rate limits are
    retried, malformed requests are surfaced as bugs rather than papered over.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        retryable: bool = False,
        status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable
        self.status = status


@runtime_checkable
class AIProvider(Protocol):
    """Implement this, register it, add contract tests. That is a whole provider."""

    name: str
    capabilities: Capabilities

    async def chat(self, request: ChatRequest) -> ChatResponse: ...

    def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]: ...

    async def embed(self, request: EmbedRequest) -> EmbedResponse: ...

    async def structured(self, request: StructuredRequest) -> dict[str, Any]: ...

    async def health(self) -> HealthReport: ...
