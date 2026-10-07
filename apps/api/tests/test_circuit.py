"""Per-provider circuit breaking and client-safe AI errors, with a fake provider."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from noema.core.errors import (
    AITimeout,
    ProviderUnavailable,
    ai_problem,
    register_error_handlers,
)
from noema.providers import gateway as gateway_module
from noema.providers.base import (
    Capabilities,
    ChatRequest,
    ChatResponse,
    CircuitOpen,
    EmbedRequest,
    EmbedResponse,
    HealthReport,
    Message,
    ProviderError,
    ProviderTimeout,
    Role,
    StreamEvent,
    StructuredRequest,
    TaskClass,
    Usage,
)
from noema.providers.circuit import (
    BreakerPolicy,
    CircuitBreaker,
    breaker_for,
    counts_as_outage,
)
from noema.providers.gateway import AIGateway, RetryPolicy
from noema.providers.mock import MockProvider

REQUEST = ChatRequest(
    messages=[Message(role=Role.USER, content="explain backpropagation")],
    task=TaskClass.TUTOR_CHAT,
)
ONE_TRY = RetryPolicy(attempts=1, base_delay=0.0, max_delay=0.0)
SECRET_TEXT = "Your credit balance is too low (org org-SECRET, key sk-ant-LEAK)"


class FakeProvider:
    """Answers with whatever `mode` says: ok, 503, 400, timeout, or transport."""

    capabilities = Capabilities(chat=True, streaming=True)

    def __init__(self, name: str = "fake", mode: str = "503") -> None:
        self.name = name
        self.mode = mode
        self.calls = 0

    async def _fail(self) -> None:
        if self.mode == "503":
            raise ProviderError(
                SECRET_TEXT, provider=self.name, retryable=True, status=503
            )
        if self.mode == "400":
            raise ProviderError(SECRET_TEXT, provider=self.name, status=400)
        if self.mode == "timeout":
            await asyncio.sleep(10)
        if self.mode == "transport":
            try:
                raise httpx.ConnectError("connection refused")
            except httpx.ConnectError as exc:
                raise ProviderError(str(exc), provider=self.name, retryable=True) from exc

    async def chat(self, request: ChatRequest) -> ChatResponse:
        self.calls += 1
        await self._fail()
        return ChatResponse(content="ok", model="fake-1", usage=Usage(1, 1))

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        self.calls += 1
        await self._fail()
        yield StreamEvent(delta="ok")
        yield StreamEvent(done=True, usage=Usage(1, 1))

    async def embed(self, request: EmbedRequest) -> EmbedResponse:
        raise NotImplementedError

    async def structured(self, request: StructuredRequest) -> dict[str, Any]:
        raise NotImplementedError

    async def health(self) -> HealthReport:
        return HealthReport(healthy=True)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


# ── the breaker itself ──────────────────────────────────────────────────────────


def outage() -> ProviderError:
    return ProviderError("x", provider="p", retryable=True, status=503)


def test_opens_after_consecutive_failures_within_the_window() -> None:
    clock = Clock()
    breaker = CircuitBreaker("p", BreakerPolicy(3, 60, 30), clock=clock)
    for _ in range(2):
        breaker.record_failure(outage())
    assert breaker.state.name == "CLOSED"
    breaker.record_failure(outage())
    assert breaker.state.name == "OPEN"
    assert not breaker.allow()


def test_failures_outside_the_window_do_not_add_up() -> None:
    clock = Clock()
    breaker = CircuitBreaker("p", BreakerPolicy(3, 60, 30), clock=clock)
    breaker.record_failure(outage())
    breaker.record_failure(outage())
    clock.now += 61
    breaker.record_failure(outage())
    assert breaker.state.name == "CLOSED"


def test_a_success_resets_the_count() -> None:
    breaker = CircuitBreaker("p", BreakerPolicy(2, 60, 30), clock=Clock())
    breaker.record_failure(outage())
    breaker.record_success()
    breaker.record_failure(outage())
    assert breaker.state.name == "CLOSED"


def test_half_open_admits_exactly_one_probe_after_cooldown() -> None:
    clock = Clock()
    breaker = CircuitBreaker("p", BreakerPolicy(1, 60, 30), clock=clock)
    breaker.record_failure(outage())
    assert not breaker.allow()
    clock.now += 30
    assert breaker.state.name == "HALF_OPEN"
    assert breaker.allow()
    assert not breaker.allow(), "a second caller must wait for the probe"


def test_a_failed_probe_reopens_and_a_good_one_closes() -> None:
    clock = Clock()
    breaker = CircuitBreaker("p", BreakerPolicy(1, 60, 30), clock=clock)
    breaker.record_failure(outage())
    clock.now += 30
    assert breaker.allow()
    breaker.record_failure(outage())
    assert breaker.state.name == "OPEN"
    clock.now += 30
    assert breaker.allow()
    breaker.record_success()
    assert breaker.state.name == "CLOSED"
    assert breaker.allow()


@pytest.mark.parametrize(
    ("exc", "counts"),
    [
        (TimeoutError(), True),
        (ProviderTimeout("t", provider="p", retryable=True), True),
        (ProviderError("x", provider="p", status=503), True),
        (ProviderError("x", provider="p", status=429), True),
        (ProviderError("x", provider="p", status=400), False),
        (ProviderError("x", provider="p", status=401), False),
        (ProviderError("bad json", provider="p", retryable=True), False),
        (KeyError("bug"), False),
    ],
)
def test_only_service_failures_count(exc: BaseException, counts: bool) -> None:
    """A 401 may be one learner's BYOK key; it must not switch the provider off."""
    assert counts_as_outage(exc) is counts


def test_a_snapshot_names_the_error_class_never_the_text() -> None:
    breaker = CircuitBreaker("p", BreakerPolicy(1, 60, 30), clock=Clock())
    breaker.record_failure(
        ProviderError(SECRET_TEXT, provider="p", retryable=True, status=503)
    )
    snap = breaker.snapshot()
    assert snap["state"] == "open"
    assert snap["last_error"] == "http_503"
    assert "SECRET" not in str(snap) and "LEAK" not in str(snap)


# ── through the gateway ────────────────────────────────────────────────────────


async def test_an_open_circuit_skips_the_provider_and_uses_the_fallback() -> None:
    broken = FakeProvider("broken", "503")
    for _ in range(5):
        gateway = AIGateway(broken, [MockProvider()], retry=ONE_TRY)
        await gateway.chat(REQUEST)
    assert breaker_for("broken").state.name == "OPEN"
    calls_when_opened = broken.calls

    response = await AIGateway(broken, [MockProvider()], retry=ONE_TRY).chat(REQUEST)

    assert "backpropagation" in response.content
    assert broken.calls == calls_when_opened, "an open circuit makes no call"


async def test_every_circuit_open_fails_fast_with_circuit_open() -> None:
    broken = FakeProvider("broken", "transport")
    for _ in range(5):
        with pytest.raises(ProviderError):
            await AIGateway(broken, retry=ONE_TRY).chat(REQUEST)
    with pytest.raises(CircuitOpen):
        await AIGateway(broken, retry=ONE_TRY).chat(REQUEST)


async def test_client_errors_never_open_the_circuit() -> None:
    bad_key = FakeProvider("byok", "400")
    for _ in range(10):
        with pytest.raises(ProviderError):
            await AIGateway(bad_key, retry=ONE_TRY).chat(REQUEST)
    assert breaker_for("byok").state.name == "CLOSED"


async def test_a_timeout_is_a_provider_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(gateway_module.TIMEOUTS, TaskClass.TUTOR_CHAT, 0.01)
    slow = FakeProvider("slow", "timeout")
    with pytest.raises(ProviderTimeout):
        await AIGateway(slow, retry=ONE_TRY).chat(REQUEST)
    assert breaker_for("slow").snapshot()["last_error"] == "timeout"


async def test_streaming_respects_the_circuit() -> None:
    broken = FakeProvider("broken", "503")
    for _ in range(5):
        events = [e async for e in AIGateway(broken, [MockProvider()]).stream(REQUEST)]
        assert events
    calls = broken.calls
    events = [e async for e in AIGateway(broken, [MockProvider()]).stream(REQUEST)]
    assert events[-1].done
    assert broken.calls == calls


# ── what the client sees ───────────────────────────────────────────────────────


def test_problems_never_carry_provider_text() -> None:
    problem = ai_problem(ProviderError(SECRET_TEXT, provider="p", status=400))
    assert isinstance(problem, ProviderUnavailable)
    assert "SECRET" not in problem.detail and "credit" not in problem.detail


def test_a_timeout_is_a_504_ai_timeout() -> None:
    problem = ai_problem(ProviderTimeout("slow timed out", provider="p", retryable=True))
    assert isinstance(problem, AITimeout)
    assert problem.status_code == 504
    assert problem.slug == "ai-timeout"


def test_an_escaped_provider_error_becomes_a_clean_problem() -> None:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise ProviderError(SECRET_TEXT, provider="anthropic", status=400)

    response = TestClient(app).get("/boom")
    assert response.status_code == 502
    body = response.json()
    assert body["type"].endswith("/provider-unavailable")
    assert "SECRET" not in response.text and "LEAK" not in response.text
