"""The landing demo streams a lesson opening and nothing else."""

from __future__ import annotations

import json
from typing import Any

import pytest

from noema.api.v1.demo import stream_demo
from noema.providers.base import (
    Capabilities,
    ChatRequest,
    ChatResponse,
    EmbedRequest,
    EmbedResponse,
    HealthReport,
    ProviderError,
    StreamEvent,
    StructuredRequest,
)
from noema.providers.gateway import AIGateway


class ScriptedProvider:
    name = "fake"
    capabilities = Capabilities(chat=True, structured_output="native")

    def __init__(self, chunks: list[str] | Exception) -> None:
        self.chunks = chunks
        self.requests: list[ChatRequest] = []

    async def chat(self, request: ChatRequest) -> ChatResponse:
        raise NotImplementedError

    async def stream(self, request: ChatRequest) -> Any:
        self.requests.append(request)
        if isinstance(self.chunks, Exception):
            raise self.chunks
        for chunk in self.chunks:
            yield StreamEvent(delta=chunk)
        yield StreamEvent(done=True)

    async def embed(self, request: EmbedRequest) -> EmbedResponse:
        raise NotImplementedError

    async def structured(self, request: StructuredRequest) -> dict[str, Any]:
        raise NotImplementedError

    async def health(self) -> HealthReport:
        raise NotImplementedError


async def collect(body: Any) -> list[tuple[str, dict[str, Any]]]:
    events = []
    async for chunk in body:
        lines = chunk.decode().strip("\n").split("\n")
        events.append(
            (
                lines[0].removeprefix("event: "),
                json.loads(lines[1].removeprefix("data: ")),
            )
        )
    return events


@pytest.mark.asyncio
async def test_demo_streams_tokens_with_the_demo_prompt_and_a_hard_cap() -> None:
    provider = ScriptedProvider(["Comece pelo ", "inconsciente."])
    events = await collect(
        stream_demo(
            "Psicologia segundo Freud", AIGateway(provider), model=None, max_tokens=120
        )
    )
    assert [name for name, _ in events] == ["token", "token", "done"]
    assert (
        "".join(d["text"] for n, d in events if n == "token")
        == "Comece pelo inconsciente."
    )

    request = provider.requests[0]
    assert request.max_tokens == 120
    assert request.messages[0].content.startswith(
        "You are NOEMA, a tutor, meeting a visitor"
    )
    assert request.messages[-1].content == "Psicologia segundo Freud"
    assert request.metadata["mode"] == "demo"


@pytest.mark.asyncio
async def test_demo_reports_an_unavailable_provider_as_an_error_event() -> None:
    provider = ScriptedProvider(ProviderError("down", provider="fake"))
    events = await collect(
        stream_demo("Italiano", AIGateway(provider), model=None, max_tokens=120)
    )
    assert events == [("error", {"message": "unavailable", "provider": "fake"})]
