"""The AI provider contract.

Every model call in NOEMA goes through this interface and through the gateway that
wraps it. Feature code never imports a vendor SDK — see ``docs/ai-providers.md``.
"""

from __future__ import annotations

import weakref
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, Protocol, runtime_checkable

__all__ = [
    "AIProvider",
    "Capabilities",
    "ChatRequest",
    "ChatResponse",
    "CircuitOpen",
    "CreditExhausted",
    "EmbedRequest",
    "EmbedResponse",
    "Message",
    "ProviderError",
    "ProviderTimeout",
    "Role",
    "StreamEvent",
    "StructuredRequest",
    "StructuredResponse",
    "TaskClass",
    "Usage",
    "is_byok",
    "mark_byok",
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
    MODERATE_CONTENT = "moderate.content"


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
    #: Of ``prompt_tokens``, how many the provider read from its prompt cache.
    #: Zero when the provider does not report it.
    cached_tokens: int = 0


@dataclass(frozen=True, slots=True)
class ChatRequest:
    messages: Sequence[Message]
    task: TaskClass
    model: str | None = None
    temperature: float = 0.2
    max_tokens: int | None = None
    stop: Sequence[str] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    #: What keeps a conversation on one provider when the gateway interleaves
    #: several (``NOEMA_AI_ROUTING``): a teaching session's id, say. None
    #: falls back to ``metadata["session_id"]``, then to the gateway's own key
    #: (the learner), then to a weighted coin toss.
    routing_key: str | None = None


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
    #: The model that served the stream, as the provider named it; set on the
    #: terminal event by providers that report it.
    model: str | None = None


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
    #: None means the gateway's per-task default (``gateway.DEFAULT_MAX_TOKENS``).
    max_tokens: int | None = None
    #: Same role as ``ChatRequest.metadata``: what the call is for
    #: (``feature``, ``session_id``), carried to the usage recorder.
    metadata: dict[str, Any] = field(default_factory=dict)
    #: Same role as ``ChatRequest.routing_key``.
    routing_key: str | None = None


@dataclass(frozen=True, slots=True)
class StructuredResponse:
    """A structured result with what it cost and who answered.

    Providers that can say expose ``structured_response(request)``; the
    gateway records its model and tokens. ``structured()`` stays the
    contract every provider implements and returns ``data`` alone.
    """

    data: dict[str, Any]
    model: str
    usage: Usage


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

    #: True when the provider did not answer in time. Lets error handling tell a
    #: slow provider (504, "try again") from a failing one without parsing text.
    timed_out = False


class ProviderTimeout(ProviderError):
    """The provider did not answer within the gateway's per-task timeout."""

    timed_out = True


class CircuitOpen(ProviderError):
    """Every provider in the chain is refusing calls after repeated failures.

    Raised by the gateway without calling anyone, so a lesson fails in
    milliseconds during an outage instead of after the whole retry ladder.
    """


class CreditExhausted(ProviderError):
    """The provider refused because the deployment's account is out of money:
    Anthropic's 400 "credit balance is too low", OpenAI's 429
    ``insufficient_quota``.

    Not the caller's fault and not fixed by retrying in a second: the provider
    is down for this account until someone pays. The circuit breaker opens at
    once, for a long cooldown, and the gateway moves to the next provider.
    """


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


#: Providers built on a learner's own key rather than the deployment's. Kept
#: beside the provider instead of on it so the contract above stays two
#: attributes; weak, so a request's providers are forgotten with the request.
_BYOK: weakref.WeakSet[Any] = weakref.WeakSet()


def mark_byok(provider: AIProvider) -> AIProvider:
    """Record that `provider` spends a learner's own key."""
    _BYOK.add(provider)
    return provider


def is_byok(provider: AIProvider) -> bool:
    return provider in _BYOK
