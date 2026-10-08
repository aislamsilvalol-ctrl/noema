"""Interleaving providers (NOEMA_AI_ROUTING), sticky keys, credit outages."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any

import httpx
import pytest

from noema.core.config import Settings, parse_tier_models
from noema.db.models import ModelTier
from noema.providers import routing as routing_module
from noema.providers.anthropic import AnthropicProvider
from noema.providers.base import (
    Capabilities,
    ChatRequest,
    ChatResponse,
    CreditExhausted,
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
    mark_byok,
)
from noema.providers.circuit import CircuitState, breaker_for, counts_as_outage
from noema.providers.gateway import AIGateway, RetryPolicy
from noema.providers.openai import OpenAIProvider
from noema.providers.routing import RoutingPolicy
from noema.services.professor import tier_models

REQUEST = ChatRequest(
    messages=[Message(role=Role.USER, content="explain backpropagation")],
    task=TaskClass.TUTOR_CHAT,
)
ONE_TRY = RetryPolicy(attempts=1, base_delay=0.0, max_delay=0.0)
CREDIT_BODY = {
    "type": "error",
    "error": {
        "type": "invalid_request_error",
        "message": "Your credit balance is too low to access the Anthropic API.",
    },
}


class Fake:
    """Answers, or fails how it is told; remembers every model it was asked for."""

    capabilities = Capabilities(chat=True, streaming=True, structured_output="native")

    def __init__(self, name: str, fail: ProviderError | None = None) -> None:
        self.name = name
        self.fail = fail
        self.calls = 0
        self.models: list[str | None] = []
        self.break_mid_stream = False

    async def chat(self, request: ChatRequest) -> ChatResponse:
        self.calls += 1
        self.models.append(request.model)
        if self.fail:
            raise self.fail
        return ChatResponse(content=self.name, model=f"{self.name}-1", usage=Usage(1, 1))

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        self.calls += 1
        self.models.append(request.model)
        if self.fail:
            raise self.fail
        yield StreamEvent(delta=self.name)
        if self.break_mid_stream:
            raise ProviderError("dropped", provider=self.name, retryable=True)
        yield StreamEvent(done=True, usage=Usage(1, 1))

    async def embed(self, request: EmbedRequest) -> EmbedResponse:
        self.calls += 1
        return EmbedResponse(
            vectors=[[0.0]], model=self.name, dimensions=1, usage=Usage()
        )

    async def structured(self, request: StructuredRequest) -> dict[str, Any]:
        self.calls += 1
        self.models.append(request.model)
        if self.fail:
            raise self.fail
        return {"by": self.name}

    async def health(self) -> HealthReport:
        return HealthReport(healthy=True)


class Recorder:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> None:
        self.rows.append(kwargs)


def credit_error(name: str = "anthropic") -> CreditExhausted:
    return CreditExhausted("out of credit", provider=name, status=400)


def routed(
    spec: str = "anthropic:50,openai:50", **kwargs: Any
) -> tuple[AIGateway, Fake, Fake]:
    anthropic, openai = Fake("anthropic"), Fake("openai")
    gateway = AIGateway(
        anthropic,
        [openai],
        retry=ONE_TRY,
        routing=RoutingPolicy.parse(spec),
        **kwargs,
    )
    return gateway, anthropic, openai


def keyed(key: str) -> ChatRequest:
    return replace(REQUEST, routing_key=key)


# ── the setting ─────────────────────────────────────────────────────────────────


def test_the_setting_parses_and_rejects_typos() -> None:
    policy = RoutingPolicy.parse(" anthropic:70 , OpenAI:30 ")
    assert policy is not None
    assert policy.weights == (("anthropic", 70.0), ("openai", 30.0))
    assert RoutingPolicy.parse("") is None
    for bad in ("anthropic", "anthropic:x", "anthropic:-1", "a:1,a:2"):
        with pytest.raises(ValueError):
            RoutingPolicy.parse(bad)


def test_a_bad_setting_stops_the_boot() -> None:
    with pytest.raises(ValueError, match="NOEMA_AI_ROUTING"):
        Settings(noema_ai_routing="anthropic=50")
    with pytest.raises(ValueError, match="NOEMA_TIER_MODELS"):
        Settings(noema_tier_models="openai.gold=gpt-4.1")


def test_unset_routing_is_no_routing() -> None:
    assert Settings().routing_policy() is None


def test_production_refuses_a_weighted_provider_without_a_key() -> None:
    settings = Settings(
        noema_default_provider="anthropic",
        anthropic_api_key="k",
        noema_embedding_provider="openai",
        openai_api_key="k",
        noema_ai_routing="anthropic:50,gemini:0,openai:50",
    )
    assert not [p for p in settings._production_dependency_problems() if "ROUTING" in p]
    settings = Settings(
        noema_default_provider="anthropic",
        anthropic_api_key="k",
        noema_ai_routing="anthropic:50,openai:50",
    )
    assert any(
        "NOEMA_AI_ROUTING names openai" in p
        for p in settings._production_dependency_problems()
    )


# ── default behaviour is unchanged ──────────────────────────────────────────────


async def test_without_routing_the_primary_answers_every_call() -> None:
    anthropic, openai = Fake("anthropic"), Fake("openai")
    gateway = AIGateway(anthropic, [openai], retry=ONE_TRY, routing_key="learner")

    for i in range(50):
        await gateway.chat(keyed(f"session-{i}"))

    assert (anthropic.calls, openai.calls) == (50, 0)


# ── weights ─────────────────────────────────────────────────────────────────────


async def test_unkeyed_calls_follow_the_weights(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routing_module, "_rng", random.Random(7))
    gateway, anthropic, openai = routed("anthropic:70,openai:30")

    for _ in range(2000):
        await gateway.chat(REQUEST)

    share = anthropic.calls / 2000
    assert 0.66 < share < 0.74, share
    assert anthropic.calls + openai.calls == 2000


async def test_keys_spread_by_weight_and_each_key_sticks() -> None:
    gateway, _, _ = routed("anthropic:50,openai:50")
    served: dict[str, str] = {}
    for i in range(2000):
        response = await gateway.chat(keyed(f"session-{i}"))
        served[f"session-{i}"] = response.content

    split = Counter(served.values())
    assert 900 < split["anthropic"] < 1100, split

    for key in list(served)[:200]:
        for _ in range(3):
            assert (await gateway.chat(keyed(key))).content == served[key]


async def test_a_weight_of_zero_drains_a_provider_to_fallback_only() -> None:
    gateway, anthropic, openai = routed("anthropic:0,openai:100")

    for i in range(100):
        await gateway.chat(keyed(f"s{i}"))
    assert (anthropic.calls, openai.calls) == (0, 100)

    openai.fail = ProviderError("down", provider="openai", retryable=True, status=503)
    response = await gateway.chat(REQUEST)
    assert response.content == "anthropic"


async def test_the_key_comes_from_the_call_then_its_session_then_the_gateway() -> None:
    gateway, _, _ = routed(routing_key="learner-1")
    by_learner = (await gateway.chat(REQUEST)).content
    for _ in range(20):
        assert (await gateway.chat(REQUEST)).content == by_learner

    sessions = {
        (await gateway.chat(replace(REQUEST, metadata={"session_id": f"s{i}"}))).content
        for i in range(40)
    }
    assert sessions == {"anthropic", "openai"}  # the session, not the learner, decides

    # A keyed gateway (the Professor keys one per lesson) behaves like the call.
    lesson = gateway.keyed("lesson-9")
    assert (await lesson.chat(REQUEST)).content == (
        await gateway.chat(keyed("lesson-9"))
    ).content


# ── circuits ────────────────────────────────────────────────────────────────────


def _key_served_by(gateway: AIGateway, name: str) -> str:
    assert gateway.routing is not None
    for i in range(1000):
        order = gateway.routing.order(gateway.chain, key=f"k{i}", eligible=lambda p: True)
        if order[0].name == name:
            return f"k{i}"
    raise AssertionError("no key")


async def test_an_open_circuit_moves_its_keys_and_only_while_open() -> None:
    gateway, anthropic, _ = routed()
    anthropics = _key_served_by(gateway, "anthropic")
    openais = _key_served_by(gateway, "openai")

    breaker_for("anthropic").record_failure(credit_error())
    assert breaker_for("anthropic").state is CircuitState.OPEN

    assert (await gateway.chat(keyed(anthropics))).content == "openai"
    assert (await gateway.chat(keyed(openais))).content == "openai"
    assert anthropic.calls == 0

    breaker_for("anthropic").record_success()
    assert (await gateway.chat(keyed(anthropics))).content == "anthropic"
    assert (await gateway.chat(keyed(openais))).content == "openai"


async def test_a_half_open_provider_gets_its_probe_from_its_own_keys() -> None:
    gateway, _, _ = routed()
    breaker = breaker_for("anthropic")
    breaker.record_failure(credit_error())
    breaker._opened_at = -1e9  # long past the cooldown
    assert breaker.state is CircuitState.HALF_OPEN

    response = await gateway.chat(keyed(_key_served_by(gateway, "anthropic")))

    assert response.content == "anthropic"
    assert breaker.snapshot()["state"] == "closed"


async def test_every_routed_call_shape_fails_over() -> None:
    gateway, anthropic, _ = routed()
    anthropic.fail = credit_error()
    key = _key_served_by(gateway, "anthropic")

    assert (await gateway.chat(keyed(key))).content == "openai"
    breaker_for("anthropic").record_success()
    structured = StructuredRequest(
        messages=REQUEST.messages, json_schema={}, task=TaskClass.CLASSIFY_INTENT
    )
    assert await gateway.structured(replace(structured, routing_key=key)) == {
        "by": "openai"
    }
    breaker_for("anthropic").record_success()
    events = [e async for e in gateway.stream(keyed(key))]
    assert events[0].delta == "openai"


async def test_embeddings_are_never_interleaved() -> None:
    gateway, _, openai = routed("anthropic:0,openai:100")

    response = await gateway.embed(EmbedRequest(texts=["x"]))

    assert response.model == "anthropic"  # the chain's own order, as before
    assert openai.calls == 0


# ── credit outages ──────────────────────────────────────────────────────────────


def test_a_credit_outage_counts_and_opens_at_once_for_long() -> None:
    assert counts_as_outage(credit_error())
    breaker = breaker_for("anthropic")
    breaker.record_failure(credit_error())

    snapshot = breaker.snapshot()
    assert snapshot["state"] == "open"
    assert snapshot["last_error"] == "credit_exhausted"
    assert snapshot["retry_in_seconds"] > 590


def anthropic_answering(
    status: int, body: dict[str, Any], hits: list[int] | None = None
) -> AnthropicProvider:
    def answer(_: httpx.Request) -> httpx.Response:
        if hits is not None:
            hits.append(1)
        return httpx.Response(status, json=body)

    transport = httpx.MockTransport(answer)
    return AnthropicProvider(
        api_key="test",
        client=httpx.AsyncClient(transport=transport, base_url="https://x"),
    )


def openai_answering(status: int, body: dict[str, Any]) -> OpenAIProvider:
    transport = httpx.MockTransport(lambda _: httpx.Response(status, json=body))
    return OpenAIProvider(
        api_key="test",
        client=httpx.AsyncClient(transport=transport, base_url="https://x"),
    )


async def test_anthropics_credit_balance_400_trips_the_circuit_and_fails_over() -> None:
    hits: list[int] = []
    anthropic = anthropic_answering(400, CREDIT_BODY, hits)
    recorder = Recorder()
    gateway = AIGateway(
        anthropic, [Fake("openai")], retry=RetryPolicy(attempts=3), record_usage=recorder
    )

    assert (await gateway.chat(REQUEST)).content == "openai"
    assert len(hits) == 1  # not retried: waiting a second does not pay the bill
    assert breaker_for("anthropic").state is CircuitState.OPEN
    assert recorder.rows[-1]["failed_over_from"] == "anthropic"

    # The next call does not ask Anthropic at all.
    assert (await gateway.chat(REQUEST)).content == "openai"
    assert len(hits) == 1


async def test_an_ordinary_400_is_still_a_caller_error() -> None:
    body = {"error": {"type": "invalid_request_error", "message": "max_tokens: bad"}}
    with pytest.raises(ProviderError) as caught:
        await anthropic_answering(400, body).chat(REQUEST)
    assert not isinstance(caught.value, CreditExhausted)
    assert not counts_as_outage(caught.value)


async def test_openais_insufficient_quota_429_is_a_credit_outage() -> None:
    body = {
        "error": {
            "message": "You exceeded your current quota.",
            "type": "insufficient_quota",
            "code": "insufficient_quota",
        }
    }
    with pytest.raises(CreditExhausted) as caught:
        await openai_answering(429, body).chat(REQUEST)
    assert not caught.value.retryable

    rate_limited = {"error": {"type": "requests", "code": "rate_limit_exceeded"}}
    with pytest.raises(ProviderError) as plain:
        await openai_answering(429, rate_limited).chat(REQUEST)
    assert not isinstance(plain.value, CreditExhausted)
    assert plain.value.retryable


async def test_a_learners_own_key_out_of_credit_does_not_trip_the_circuit() -> None:
    byok = mark_byok(Fake("anthropic", fail=credit_error()))
    gateway = AIGateway(byok, [Fake("openai")], retry=ONE_TRY)

    assert (await gateway.chat(REQUEST)).content == "openai"
    assert breaker_for("anthropic").state is CircuitState.CLOSED


# ── streaming never splices ─────────────────────────────────────────────────────


async def test_a_stream_that_breaks_after_its_first_token_is_not_spliced() -> None:
    gateway, anthropic, openai = routed()
    key = _key_served_by(gateway, "anthropic")
    anthropic.break_mid_stream = True

    received: list[str] = []
    with pytest.raises(ProviderError):
        async for event in gateway.stream(keyed(key)):
            received.append(event.delta)

    assert received == ["anthropic"]
    assert openai.calls == 0


# ── model parity ────────────────────────────────────────────────────────────────


async def test_a_tier_call_runs_on_each_providers_own_model_for_that_tier() -> None:
    models = tier_models(ModelTier.ECONOMY, Settings())
    gateway, anthropic, openai = routed(
        models={k: v for k, v in models.items() if k != "anthropic"}
    )
    request = replace(REQUEST, model="claude-haiku-4-5-20251001")

    for i in range(40):
        await gateway.chat(replace(request, routing_key=f"s{i}"))

    assert set(anthropic.models) == {"claude-haiku-4-5-20251001"}
    assert set(openai.models) == {"gpt-4.1-mini"}


def test_every_tier_has_a_model_on_both_providers() -> None:
    for tier in ModelTier:
        models = tier_models(tier, Settings())
        assert models.get("anthropic") and models.get("openai"), tier


def test_tier_models_can_be_overridden() -> None:
    assert parse_tier_models("openai.premium=gpt-5") == {("openai", "premium"): "gpt-5"}
    settings = Settings(noema_tier_models="openai.premium=gpt-x")
    assert tier_models(ModelTier.PREMIUM, settings)["openai"] == "gpt-x"
    assert tier_models(ModelTier.STANDARD, settings)["openai"] == "gpt-4.1"


# ── observability ───────────────────────────────────────────────────────────────


async def test_usage_rows_say_who_served_and_who_it_failed_over_from() -> None:
    recorder = Recorder()
    gateway, anthropic, _ = routed(record_usage=recorder)
    key = _key_served_by(gateway, "anthropic")

    await gateway.chat(keyed(key))
    assert recorder.rows[-1]["provider"] == "anthropic"
    assert recorder.rows[-1]["failed_over_from"] is None

    anthropic.fail = ProviderError(
        "down", provider="anthropic", retryable=True, status=503
    )
    await gateway.chat(keyed(key))
    assert recorder.rows[-1]["provider"] == "openai"
    assert recorder.rows[-1]["failed_over_from"] == "anthropic"
