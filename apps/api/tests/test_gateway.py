from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any

import pytest

from noema.core.errors import QuotaExceeded
from noema.providers.base import (
    Capabilities,
    ChatRequest,
    ChatResponse,
    EmbedRequest,
    EmbedResponse,
    HealthReport,
    Message,
    ProviderError,
    Role,
    StreamEvent,
    StructuredRequest,
    StructuredResponse,
    TaskClass,
    Usage,
)
from noema.providers.gateway import AIGateway, RetryPolicy
from noema.providers.mock import MockProvider

REQUEST = ChatRequest(
    messages=[Message(role=Role.USER, content="explain backpropagation")],
    task=TaskClass.TUTOR_CHAT,
)

NO_RETRY = RetryPolicy(attempts=2, base_delay=0.0, max_delay=0.0)


class FlakyProvider:
    """Fails a set number of times, then succeeds."""

    name = "flaky"
    capabilities = Capabilities(chat=True, streaming=True)

    def __init__(self, failures: int, retryable: bool = True) -> None:
        self.remaining = failures
        self.retryable = retryable
        self.attempts = 0

    async def chat(self, request: ChatRequest) -> ChatResponse:
        self.attempts += 1
        if self.remaining > 0:
            self.remaining -= 1
            raise ProviderError("boom", provider=self.name, retryable=self.retryable)
        return ChatResponse(content="ok", model="flaky-1", usage=Usage(10, 5))

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        self.attempts += 1
        if self.remaining > 0:
            self.remaining -= 1
            raise ProviderError("boom", provider=self.name, retryable=True)
        yield StreamEvent(delta="ok")
        yield StreamEvent(done=True, usage=Usage(1, 1))

    async def embed(self, request: EmbedRequest) -> EmbedResponse:
        raise ProviderError("no embeddings", provider=self.name)

    async def structured(self, request: StructuredRequest) -> dict[str, Any]:
        raise ProviderError("no structured", provider=self.name)

    async def health(self) -> HealthReport:
        return HealthReport(healthy=self.remaining == 0)


class RecordingUsage:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> None:
        self.rows.append(kwargs)


async def test_successful_call_passes_through() -> None:
    gateway = AIGateway(MockProvider())
    response = await gateway.chat(REQUEST)
    assert "backpropagation" in response.content


async def test_retries_a_transient_failure() -> None:
    provider = FlakyProvider(failures=2)
    gateway = AIGateway(provider, retry=RetryPolicy(attempts=3, base_delay=0.0))

    response = await gateway.chat(REQUEST)

    assert response.content == "ok"
    assert provider.attempts == 3


async def test_does_not_retry_a_client_error() -> None:
    """A 400 is our bug. Retrying it wastes time and hides the cause."""
    provider = FlakyProvider(failures=5, retryable=False)
    gateway = AIGateway(provider, retry=RetryPolicy(attempts=3, base_delay=0.0))

    with pytest.raises(ProviderError):
        await gateway.chat(REQUEST)

    assert provider.attempts == 1


async def test_falls_back_to_the_next_provider() -> None:
    broken = FlakyProvider(failures=99)
    gateway = AIGateway(broken, fallbacks=[MockProvider()], retry=NO_RETRY)

    response = await gateway.chat(REQUEST)

    assert "backpropagation" in response.content


class ModelRecorder(FlakyProvider):
    """Succeeds, and remembers which model each call asked for."""

    def __init__(self) -> None:
        super().__init__(failures=0)
        self.models: list[str | None] = []

    async def chat(self, request: ChatRequest) -> ChatResponse:
        self.models.append(request.model)
        return await super().chat(request)

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        self.models.append(request.model)
        async for event in super().stream(request):
            yield event


async def test_a_fallback_runs_on_its_own_model_not_the_primarys() -> None:
    """Production, 2026-09-25: Anthropic out of credit, and OpenAI answering
    every lesson with a 404 because it was asked for `claude-sonnet-5`."""
    primary = ModelRecorder()
    primary.remaining = 99
    fallback = ModelRecorder()
    gateway = AIGateway(primary, fallbacks=[fallback], retry=NO_RETRY)
    request = replace(REQUEST, model="claude-sonnet-5")

    await gateway.chat(request)
    [event async for event in gateway.stream(request)]

    assert primary.models and set(primary.models) == {"claude-sonnet-5"}
    assert fallback.models == [None, None]


async def test_raises_when_every_provider_is_exhausted() -> None:
    gateway = AIGateway(
        FlakyProvider(failures=99), fallbacks=[FlakyProvider(failures=99)], retry=NO_RETRY
    )
    with pytest.raises(ProviderError):
        await gateway.chat(REQUEST)


async def test_usage_is_recorded_for_successes_and_failures() -> None:
    recorder = RecordingUsage()
    gateway = AIGateway(MockProvider(), record_usage=recorder)
    await gateway.chat(REQUEST)
    assert recorder.rows[-1]["succeeded"] is True
    assert recorder.rows[-1]["usage"].prompt_tokens > 0

    failing = AIGateway(FlakyProvider(failures=99), retry=NO_RETRY, record_usage=recorder)
    with pytest.raises(ProviderError):
        await failing.chat(REQUEST)
    assert recorder.rows[-1]["succeeded"] is False


async def test_streaming_yields_tokens_then_a_terminal_event() -> None:
    gateway = AIGateway(MockProvider())
    events = [event async for event in gateway.stream(REQUEST)]

    assert events[-1].done
    assert events[-1].usage is not None
    assert "".join(e.delta for e in events[:-1]).strip().endswith("backpropagation")


async def test_streaming_falls_back_before_the_first_token_only() -> None:
    """Switching model mid-answer would splice two voices into one reply."""
    gateway = AIGateway(
        FlakyProvider(failures=99), fallbacks=[MockProvider()], retry=NO_RETRY
    )

    events = [event async for event in gateway.stream(REQUEST)]

    assert events[-1].done
    assert any(e.delta for e in events)


class Budget:
    def __init__(self, remaining: int, reserved: int = 0) -> None:
        self._remaining = remaining
        self.reserved_tokens = reserved

    async def remaining_tokens(self) -> int:
        return self._remaining


async def test_budget_ceiling_degrades_with_a_clear_message() -> None:
    gateway = AIGateway(MockProvider(), budget=Budget(0))
    with pytest.raises(QuotaExceeded, match="budget"):
        await gateway.chat(REQUEST)


async def test_generation_stops_before_the_tutor_does() -> None:
    """The reserve is the whole point of the ceiling being graceful.

    A runaway generation loop should cost tomorrow's card drafts, not the ability
    to ask a question about the chapter being read right now.
    """
    gateway = AIGateway(MockProvider(), budget=Budget(remaining=500, reserved=1000))

    with pytest.raises(QuotaExceeded, match="Generation is paused"):
        await gateway.chat(replace(REQUEST, task=TaskClass.GENERATE_CARDS))

    answer = await gateway.chat(replace(REQUEST, task=TaskClass.TUTOR_CHAT))
    assert answer.content, "the tutor stopped answering while the budget still had room"


async def test_the_reserve_is_not_a_second_budget() -> None:
    """Once the budget is genuinely gone, interactive work stops too.

    A reserve that never empties is not a ceiling.
    """
    gateway = AIGateway(MockProvider(), budget=Budget(remaining=0, reserved=1000))
    with pytest.raises(QuotaExceeded):
        await gateway.chat(replace(REQUEST, task=TaskClass.TUTOR_CHAT))


async def test_retry_backoff_is_jittered_and_capped() -> None:
    policy = RetryPolicy(base_delay=1.0, max_delay=4.0)
    delays = [policy.delay(attempt) for attempt in range(5) for _ in range(20)]
    assert all(0 <= d <= 4.0 for d in delays)
    assert len(set(delays)) > 1  # jitter, not a fixed ladder


# ── the default output ceiling ─────────────────────────────────────────────
#
# A caller that sets no `max_tokens` used to get whatever the provider's
# ceiling was. Now the gateway fills in a per-task cap, and leaves an
# explicit value -- the Professor budgets every turn -- exactly as it was.


class RecordingProvider:
    name = "recording"
    capabilities = Capabilities(chat=True, streaming=True, structured_output="native")

    def __init__(self) -> None:
        self.seen: list[ChatRequest | StructuredRequest] = []

    async def chat(self, request: ChatRequest) -> ChatResponse:
        self.seen.append(request)
        return ChatResponse(content="ok", model="rec-1", usage=Usage(1, 1))

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        self.seen.append(request)
        yield StreamEvent(delta="ok")
        yield StreamEvent(done=True, usage=Usage(1, 1))

    async def embed(self, request: EmbedRequest) -> EmbedResponse:
        raise NotImplementedError

    async def structured(self, request: StructuredRequest) -> dict[str, Any]:
        self.seen.append(request)
        return {}

    async def health(self) -> HealthReport:
        return HealthReport(healthy=True)


async def test_a_chat_without_a_cap_gets_the_tasks_default() -> None:
    provider = RecordingProvider()

    await AIGateway(provider).chat(REQUEST)
    async for _ in AIGateway(provider).stream(REQUEST):
        pass

    assert [r.max_tokens for r in provider.seen] == [2048, 2048]


async def test_an_explicit_cap_is_left_alone() -> None:
    provider = RecordingProvider()

    await AIGateway(provider).chat(replace(REQUEST, max_tokens=9000))

    assert provider.seen[0].max_tokens == 9000


async def test_structured_calls_are_capped_per_task() -> None:
    provider = RecordingProvider()
    gateway = AIGateway(provider)

    for task in (TaskClass.GRADE_OPEN_ANSWER, TaskClass.GENERATE_CARDS):
        await gateway.structured(
            StructuredRequest(messages=REQUEST.messages, json_schema={}, task=task)
        )

    # Grading is a score and a sentence; generation keeps the 4096 that
    # Anthropic's structured path always sent, so no batch gets shorter.
    assert [r.max_tokens for r in provider.seen] == [1024, 4096]


class ServedBy(FlakyProvider):
    """Answers as a provider that names the model it ran on."""

    def __init__(self, name: str, served: str) -> None:
        super().__init__(failures=0)
        self.name = name
        self.served = served

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(delta="ok")
        yield StreamEvent(done=True, usage=Usage(30, 4), model=self.served)

    async def structured(self, request: StructuredRequest) -> dict[str, Any]:
        return (await self.structured_response(request)).data

    async def structured_response(self, request: StructuredRequest) -> StructuredResponse:
        return StructuredResponse({"signal": "asks"}, self.served, Usage(120, 9))


async def test_a_failed_over_call_records_the_model_and_tokens_that_served_it() -> None:
    """2026-10-07 eval: ai_usage wrote OpenAI's structured answers with 0
    tokens under the model asked of Anthropic, and fallback streams as
    "unknown"; every row priced at $0."""
    recorder = RecordingUsage()
    gateway = AIGateway(
        FlakyProvider(failures=99),
        fallbacks=[ServedBy("openai", "gpt-4.1-mini-2025-04-14")],
        retry=NO_RETRY,
        record_usage=recorder,
        models={"openai": "gpt-4.1-mini"},
    )
    structured = StructuredRequest(
        messages=[Message(role=Role.USER, content="x")],
        json_schema={"type": "object"},
        task=TaskClass.CLASSIFY_INTENT,
        model="claude-haiku-4-5-20251001",
    )

    assert await gateway.structured(structured) == {"signal": "asks"}
    [event async for event in gateway.stream(replace(REQUEST, model="claude-sonnet-5"))]

    served = [row for row in recorder.rows if row["succeeded"]]
    assert [(r["provider"], r["model"]) for r in served] == [
        ("openai", "gpt-4.1-mini-2025-04-14"),
        ("openai", "gpt-4.1-mini-2025-04-14"),
    ]
    assert served[0]["usage"] == Usage(120, 9)
    assert served[1]["usage"] == Usage(30, 4)
    assert all(r["failed_over_from"] == "flaky" for r in served)


async def test_a_stream_without_a_named_model_records_the_providers_default() -> None:
    recorder = RecordingUsage()
    fallback = MockProvider()
    fallback.model = "mock-default"  # type: ignore[attr-defined]
    gateway = AIGateway(
        FlakyProvider(failures=99),
        fallbacks=[fallback],
        retry=NO_RETRY,
        record_usage=recorder,
    )

    [event async for event in gateway.stream(replace(REQUEST, model="claude-sonnet-5"))]

    assert recorder.rows[-1]["model"] == "mock-default"
