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
