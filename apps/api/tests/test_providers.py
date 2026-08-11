"""Contract tests every provider must pass, plus per-provider wire-format checks."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from noema.core.errors import FeatureUnavailable
from noema.providers.anthropic import AnthropicProvider
from noema.providers.base import (
    AIProvider,
    ChatRequest,
    EmbedRequest,
    Message,
    ProviderError,
    Role,
    StructuredRequest,
    TaskClass,
)
from noema.providers.mock import MockProvider
from noema.providers.ollama import OllamaProvider
from noema.providers.openai import OpenAIProvider
from noema.providers.registry import UnknownProvider, available, create

CHAT = ChatRequest(
    messages=[Message(role=Role.USER, content="what is a derivative")],
    task=TaskClass.TUTOR_CHAT,
)

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"name": {"type": "string"}, "difficulty": {"type": "number"}},
    "required": ["name", "difficulty"],
}


def transport(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://test")


# ── Contract ──────────────────────────────────────────────────────────────────


@pytest.fixture(params=["mock"])
def provider(request: pytest.FixtureRequest) -> AIProvider:
    return create(request.param)


def test_every_provider_declares_a_name_and_capabilities(provider: AIProvider) -> None:
    assert provider.name
    assert isinstance(provider.capabilities.max_context, int)
    assert provider.capabilities.max_context > 0


async def test_chat_returns_content_and_usage(provider: AIProvider) -> None:
    if not provider.capabilities.chat:
        pytest.skip("no chat")
    response = await provider.chat(CHAT)
    assert response.content
    assert response.usage.prompt_tokens >= 0


async def test_stream_terminates_with_done(provider: AIProvider) -> None:
    if not provider.capabilities.streaming:
        pytest.skip("no streaming")
    events = [e async for e in provider.stream(CHAT)]
    assert events[-1].done


async def test_structured_output_validates_against_its_schema(provider: AIProvider) -> None:
    if provider.capabilities.structured_output == "none":
        pytest.skip("no structured output")
    result = await provider.structured(
        StructuredRequest(
            messages=CHAT.messages, json_schema=SCHEMA, task=TaskClass.EXTRACT_CONCEPTS
        )
    )
    assert set(SCHEMA["required"]) <= set(result)


# ── Mock ──────────────────────────────────────────────────────────────────────


async def test_mock_embeddings_are_deterministic_and_normalised() -> None:
    mock = MockProvider(dimensions=64)
    first = await mock.embed(EmbedRequest(texts=["gradient descent"]))
    second = await mock.embed(EmbedRequest(texts=["gradient descent"]))

    assert first.vectors == second.vectors
    assert first.dimensions == 64
    assert abs(sum(v * v for v in first.vectors[0]) - 1.0) < 1e-9


async def test_mock_distinguishes_different_texts() -> None:
    mock = MockProvider(dimensions=32)
    response = await mock.embed(EmbedRequest(texts=["chain rule", "linear algebra"]))
    assert response.vectors[0] != response.vectors[1]


# ── Registry ──────────────────────────────────────────────────────────────────


def test_registry_lists_registered_providers() -> None:
    names = available()
    assert {"mock", "ollama", "anthropic", "openai"} <= set(names)


def test_local_mode_hides_network_providers() -> None:
    names = available(local_mode=True)
    assert "ollama" in names
    assert "anthropic" not in names and "openai" not in names


def test_local_mode_refuses_to_build_a_network_provider() -> None:
    """The guarantee is enforced by code, not by hiding a menu item."""
    with pytest.raises(FeatureUnavailable, match="local mode"):
        create("anthropic", local_mode=True, api_key="sk-ant-whatever")


def test_unknown_provider_names_the_alternatives() -> None:
    with pytest.raises(UnknownProvider, match="mock"):
        create("definitely-not-a-provider")


# ── Ollama ────────────────────────────────────────────────────────────────────


async def test_ollama_chat_maps_the_wire_format() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is False
        return httpx.Response(
            200,
            json={
                "message": {"content": "A derivative measures instantaneous change."},
                "done": True,
                "prompt_eval_count": 12,
                "eval_count": 7,
            },
        )

    provider = OllamaProvider(client=transport(handler))
    response = await provider.chat(CHAT)

    assert response.content.startswith("A derivative")
    assert response.usage.prompt_tokens == 12
    assert response.usage.completion_tokens == 7


async def test_ollama_streams_ndjson() -> None:
    lines = [
        json.dumps({"message": {"content": "Grad"}}),
        json.dumps({"message": {"content": "ient"}}),
        json.dumps({"done": True, "prompt_eval_count": 3, "eval_count": 2}),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content="\n".join(lines))

    provider = OllamaProvider(client=transport(handler))
    events = [e async for e in provider.stream(CHAT)]

    assert "".join(e.delta for e in events) == "Gradient"
    assert events[-1].done and events[-1].usage is not None


async def test_ollama_rejects_non_json_structured_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": "sorry, here's some prose"}})

    provider = OllamaProvider(client=transport(handler))
    with pytest.raises(ProviderError, match="valid JSON"):
        await provider.structured(
            StructuredRequest(
                messages=CHAT.messages, json_schema=SCHEMA, task=TaskClass.EXTRACT_CONCEPTS
            )
        )


async def test_ollama_connection_failure_says_what_to_do() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    provider = OllamaProvider(client=transport(handler))
    with pytest.raises(ProviderError, match="Is it running"):
        await provider.chat(CHAT)


# ── Anthropic ─────────────────────────────────────────────────────────────────


async def test_anthropic_hoists_system_messages_to_the_top_level() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "hello"}],
                "model": "claude-sonnet-4-5",
                "usage": {"input_tokens": 5, "output_tokens": 2},
                "stop_reason": "end_turn",
            },
        )

    provider = AnthropicProvider(api_key="sk-ant-test", client=transport(handler))
    await provider.chat(
        ChatRequest(
            messages=[
                Message(role=Role.SYSTEM, content="be terse"),
                Message(role=Role.USER, content="hi"),
            ],
            task=TaskClass.TUTOR_CHAT,
        )
    )

    assert captured["system"] == "be terse"
    assert [m["role"] for m in captured["messages"]] == ["user"]


async def test_anthropic_structured_output_uses_a_forced_tool_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["tool_choice"] == {"type": "tool", "name": "respond"}
        return httpx.Response(
            200,
            json={
                "content": [
                    {"type": "tool_use", "name": "respond", "input": {"name": "Chain Rule", "difficulty": 0.6}}
                ],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    provider = AnthropicProvider(api_key="sk-ant-test", client=transport(handler))
    result = await provider.structured(
        StructuredRequest(
            messages=CHAT.messages, json_schema=SCHEMA, task=TaskClass.EXTRACT_CONCEPTS
        )
    )
    assert result == {"name": "Chain Rule", "difficulty": 0.6}


async def test_anthropic_points_elsewhere_for_embeddings() -> None:
    provider = AnthropicProvider(api_key="sk-ant-test", client=transport(lambda r: httpx.Response(200)))
    with pytest.raises(ProviderError, match="NOEMA_EMBEDDING_PROVIDER"):
        await provider.embed(EmbedRequest(texts=["x"]))


async def test_anthropic_missing_key_fails_at_construction() -> None:
    with pytest.raises(ProviderError, match="required"):
        AnthropicProvider(api_key="")


@pytest.mark.parametrize(
    ("status", "retryable"), [(400, False), (401, False), (429, True), (500, True), (503, True)]
)
async def test_retryability_matches_the_status_class(status: int, retryable: bool) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": "nope"})

    provider = AnthropicProvider(api_key="sk-ant-test", client=transport(handler))
    with pytest.raises(ProviderError) as exc:
        await provider.chat(CHAT)
    assert exc.value.retryable is retryable


# ── OpenAI ────────────────────────────────────────────────────────────────────


async def test_openai_embeddings_preserve_input_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                # Deliberately out of order: the API does not promise sorted output.
                "data": [
                    {"index": 1, "embedding": [0.3, 0.4]},
                    {"index": 0, "embedding": [0.1, 0.2]},
                ],
                "usage": {"prompt_tokens": 4},
            },
        )

    provider = OpenAIProvider(api_key="sk-test", client=transport(handler))
    response = await provider.embed(EmbedRequest(texts=["first", "second"]))

    assert response.vectors == [[0.1, 0.2], [0.3, 0.4]]


async def test_openai_streams_sse_until_done() -> None:
    body = (
        'data: {"choices":[{"delta":{"content":"Grad"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"ient"}}]}\n\n'
        'data: {"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":2}}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    provider = OpenAIProvider(api_key="sk-test", client=transport(handler))
    events = [e async for e in provider.stream(CHAT)]

    assert "".join(e.delta for e in events) == "Gradient"
    assert events[-1].done
    assert events[-1].usage is not None and events[-1].usage.completion_tokens == 2
