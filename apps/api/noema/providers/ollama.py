"""Ollama provider — the default in local mode.

Ollama has no native JSON-schema mode, so structured output goes through the prompted
path with schema validation and retry. That is also why mastery discounts AI-graded
evidence when running locally (``docs/mastery-engine.md``, ``w_src``).
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

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
    Usage,
)
from noema.providers.registry import register

DEFAULT_CHAT_MODEL = "llama3.1"
DEFAULT_EMBED_MODEL = "nomic-embed-text"


@register("ollama")
class OllamaProvider:
    name = "ollama"
    capabilities = Capabilities(
        chat=True,
        streaming=True,
        embeddings=True,
        structured_output="prompted",
        vision=False,
        max_context=32_000,
        max_output=4_096,
    )

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        chat_model: str = DEFAULT_CHAT_MODEL,
        embed_model: str = DEFAULT_EMBED_MODEL,
        timeout: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.chat_model = chat_model
        self.embed_model = embed_model
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def chat(self, request: ChatRequest) -> ChatResponse:
        payload = self._chat_payload(request, stream=False)
        data = await self._post("/api/chat", payload)
        content = data.get("message", {}).get("content", "")
        return ChatResponse(
            content=content,
            model=payload["model"],
            usage=Usage(
                prompt_tokens=data.get("prompt_eval_count", 0),
                completion_tokens=data.get("eval_count", 0),
            ),
            finish_reason="stop" if data.get("done") else "length",
        )

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        payload = self._chat_payload(request, stream=True)
        try:
            async with self._client.stream(
                "POST", f"{self.base_url}/api/chat", json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if chunk.get("done"):
                        yield StreamEvent(
                            done=True,
                            usage=Usage(
                                prompt_tokens=chunk.get("prompt_eval_count", 0),
                                completion_tokens=chunk.get("eval_count", 0),
                            ),
                        )
                        return
                    delta = chunk.get("message", {}).get("content", "")
                    if delta:
                        yield StreamEvent(delta=delta)
        except httpx.HTTPError as exc:
            raise self._error(exc) from exc

    async def embed(self, request: EmbedRequest) -> EmbedResponse:
        model = request.model or self.embed_model
        data = await self._post(
            "/api/embed", {"model": model, "input": list(request.texts)}
        )
        vectors = data.get("embeddings", [])
        if not vectors:
            raise ProviderError("empty embedding response", provider=self.name)
        return EmbedResponse(
            vectors=vectors,
            model=model,
            dimensions=len(vectors[0]),
            usage=Usage(prompt_tokens=data.get("prompt_eval_count", 0)),
        )

    async def structured(self, request: StructuredRequest) -> dict[str, Any]:
        """Prompted JSON with Ollama's ``format`` hint. Validation is the caller's."""
        payload = {
            "model": request.model or self.chat_model,
            "messages": [
                {"role": m.role.value, "content": m.content} for m in request.messages
            ],
            "format": request.json_schema,
            "stream": False,
            "options": {"temperature": 0.0},
        }
        data = await self._post("/api/chat", payload)
        content = data.get("message", {}).get("content", "")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ProviderError(
                "model did not return valid JSON", provider=self.name, retryable=True
            ) from exc
        if not isinstance(parsed, dict):
            raise ProviderError(
                "expected a JSON object", provider=self.name, retryable=True
            )
        return parsed

    async def health(self) -> HealthReport:
        started = time.perf_counter()
        try:
            response = await self._client.get(f"{self.base_url}/api/tags", timeout=5.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            return HealthReport(healthy=False, detail=f"{type(exc).__name__}: {exc}")
        return HealthReport(
            healthy=True, latency_ms=(time.perf_counter() - started) * 1000
        )

    def _chat_payload(self, request: ChatRequest, *, stream: bool) -> dict[str, Any]:
        options: dict[str, Any] = {"temperature": request.temperature}
        if request.max_tokens:
            options["num_predict"] = request.max_tokens
        if request.stop:
            options["stop"] = list(request.stop)
        return {
            "model": request.model or self.chat_model,
            "messages": [
                {"role": m.role.value, "content": m.content} for m in request.messages
            ],
            "stream": stream,
            "options": options,
        }

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.post(f"{self.base_url}{path}", json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise self._error(exc, exc.response.status_code) from exc
        except httpx.HTTPError as exc:
            raise self._error(exc) from exc
        return dict(response.json())

    def _error(self, exc: Exception, status: int | None = None) -> ProviderError:
        # Connection failures against a local daemon are almost always "not running",
        # so say that instead of surfacing a transport traceback.
        if status is None:
            return ProviderError(
                f"Could not reach Ollama at {self.base_url}. Is it running?",
                provider=self.name,
                retryable=True,
            )
        return ProviderError(
            f"Ollama returned {status}",
            provider=self.name,
            retryable=status >= 500,
            status=status,
        )
