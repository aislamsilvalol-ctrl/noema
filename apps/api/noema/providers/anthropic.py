"""Anthropic provider.

Declares ``embeddings: False``. Capability negotiation routes embeddings to whatever
provider is configured for that task, so pairing Claude for reasoning with a local
embedding model is an ordinary configuration rather than a special case.

Uses the HTTP API directly instead of the SDK: one fewer dependency, and the wire
format is small enough that the indirection would cost more than it saves.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

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
    Usage,
)
from noema.providers.registry import register

API_BASE = "https://api.anthropic.com/v1"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-4-5"


@register("anthropic")
class AnthropicProvider:
    name = "anthropic"
    capabilities = Capabilities(
        chat=True,
        streaming=True,
        embeddings=False,
        structured_output="tool_call",
        vision=True,
        max_context=200_000,
        max_output=8_192,
    )

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        timeout: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ProviderError("Anthropic API key is required", provider=self.name)
        self.model = model
        self._client = client or httpx.AsyncClient(
            timeout=timeout,
            base_url=API_BASE,
            headers={
                "x-api-key": api_key,
                "anthropic-version": API_VERSION,
                "content-type": "application/json",
            },
        )

    async def chat(self, request: ChatRequest) -> ChatResponse:
        payload = self._payload(request, stream=False)
        data = await self._post("/messages", payload)
        content = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        )
        usage = data.get("usage", {})
        return ChatResponse(
            content=content,
            model=data.get("model", payload["model"]),
            usage=Usage(
                prompt_tokens=usage.get("input_tokens", 0),
                completion_tokens=usage.get("output_tokens", 0),
            ),
            finish_reason="length" if data.get("stop_reason") == "max_tokens" else "stop",
        )

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        payload = self._payload(request, stream=True)
        prompt_tokens = 0
        completion_tokens = 0
        try:
            async with self._client.stream("POST", "/messages", json=payload) as response:
                await self._raise_for_status(response)
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    event = json.loads(line[6:])
                    kind = event.get("type")
                    if kind == "message_start":
                        prompt_tokens = event["message"]["usage"].get("input_tokens", 0)
                    elif kind == "content_block_delta":
                        delta = event.get("delta", {}).get("text", "")
                        if delta:
                            yield StreamEvent(delta=delta)
                    elif kind == "message_delta":
                        completion_tokens = event.get("usage", {}).get("output_tokens", 0)
                    elif kind == "message_stop":
                        yield StreamEvent(
                            done=True,
                            usage=Usage(prompt_tokens, completion_tokens),
                        )
                        return
        except httpx.HTTPError as exc:
            raise ProviderError(str(exc), provider=self.name, retryable=True) from exc

    async def embed(self, request: EmbedRequest) -> EmbedResponse:
        raise ProviderError(
            "Anthropic does not provide embeddings. Configure NOEMA_EMBEDDING_PROVIDER "
            "with a provider that does (openai, gemini or ollama).",
            provider=self.name,
        )

    async def structured(self, request: StructuredRequest) -> dict[str, Any]:
        """Schema-constrained output via a forced tool call."""
        payload: dict[str, Any] = {
            "model": request.model or self.model,
            "max_tokens": 4096,
            "messages": [
                {"role": m.role.value, "content": m.content}
                for m in request.messages
                if m.role is not Role.SYSTEM
            ],
            "tools": [
                {
                    "name": "respond",
                    "description": "Return the structured result.",
                    "input_schema": request.json_schema,
                }
            ],
            "tool_choice": {"type": "tool", "name": "respond"},
        }
        system = self._system(request.messages)
        if system:
            payload["system"] = system

        data = await self._post("/messages", payload)
        for block in data.get("content", []):
            if block.get("type") == "tool_use":
                return dict(block.get("input", {}))
        raise ProviderError(
            "model did not return the structured tool call",
            provider=self.name,
            retryable=True,
        )

    async def health(self) -> HealthReport:
        started = time.perf_counter()
        try:
            await self._post(
                "/messages",
                {
                    "model": self.model,
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "ping"}],
                },
            )
        except ProviderError as exc:
            return HealthReport(healthy=False, detail=str(exc))
        return HealthReport(
            healthy=True, latency_ms=(time.perf_counter() - started) * 1000
        )

    def _payload(self, request: ChatRequest, *, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model or self.model,
            "max_tokens": request.max_tokens or self.capabilities.max_output,
            "temperature": request.temperature,
            "stream": stream,
            "messages": [
                {"role": m.role.value, "content": m.content}
                for m in request.messages
                if m.role is not Role.SYSTEM
            ],
        }
        system = self._system(request.messages)
        if system:
            payload["system"] = system
        if request.stop:
            payload["stop_sequences"] = list(request.stop)
        return payload

    @staticmethod
    def _system(messages: Sequence[Message]) -> str:
        # Anthropic takes the system prompt as a top-level field, not a message.
        return "\n\n".join(m.content for m in messages if m.role is Role.SYSTEM)

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.post(path, json=payload)
            await self._raise_for_status(response)
        except httpx.HTTPError as exc:
            raise ProviderError(str(exc), provider=self.name, retryable=True) from exc
        return dict(response.json())

    async def _raise_for_status(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        status = response.status_code
        # 429 and 5xx are worth retrying; a 400 is our bug and must surface as one.
        raise ProviderError(
            f"Anthropic returned {status}",
            provider=self.name,
            retryable=status == 429 or status >= 500,
            status=status,
        )
