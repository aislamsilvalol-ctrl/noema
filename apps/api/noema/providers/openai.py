"""OpenAI provider — chat, streaming, embeddings and native structured output."""

from __future__ import annotations

import copy
import json
import time
from collections.abc import AsyncIterator
from typing import Any, cast

import httpx

from noema.core.logging import get_logger
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

log = get_logger(__name__)

API_BASE = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_EMBED_MODEL = "text-embedding-3-small"
#: A non-2xx body is a small JSON error object, never worth logging past this --
#: this exists to bound an unexpected huge/malformed body, not to truncate a
#: normal one.
MAX_ERROR_DETAIL_CHARS = 1000


@register("openai")
class OpenAIProvider:
    name = "openai"
    capabilities = Capabilities(
        chat=True,
        streaming=True,
        embeddings=True,
        structured_output="native",
        vision=True,
        max_context=128_000,
        max_output=16_384,
    )

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        embed_model: str = DEFAULT_EMBED_MODEL,
        base_url: str = API_BASE,
        timeout: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ProviderError("OpenAI API key is required", provider=self.name)
        self.model = model
        self.embed_model = embed_model
        self._client = client or httpx.AsyncClient(
            timeout=timeout,
            base_url=base_url,
            headers={
                "authorization": f"Bearer {api_key}",
                "content-type": "application/json",
            },
        )

    async def chat(self, request: ChatRequest) -> ChatResponse:
        data = await self._post("/chat/completions", self._payload(request, stream=False))
        choice = data["choices"][0]
        usage = data.get("usage", {})
        return ChatResponse(
            content=choice["message"].get("content") or "",
            model=data.get("model", self.model),
            usage=Usage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
            ),
            finish_reason="length" if choice.get("finish_reason") == "length" else "stop",
        )

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        payload = self._payload(request, stream=True)
        payload["stream_options"] = {"include_usage": True}
        usage = Usage()
        try:
            async with self._client.stream(
                "POST", "/chat/completions", json=payload
            ) as response:
                await self._raise_for_status(response)
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    body = line[6:]
                    if body.strip() == "[DONE]":
                        yield StreamEvent(done=True, usage=usage)
                        return
                    event = json.loads(body)
                    if event.get("usage"):
                        usage = Usage(
                            prompt_tokens=event["usage"].get("prompt_tokens", 0),
                            completion_tokens=event["usage"].get("completion_tokens", 0),
                        )
                    for choice in event.get("choices", []):
                        delta = choice.get("delta", {}).get("content")
                        if delta:
                            yield StreamEvent(delta=delta)
        except httpx.HTTPError as exc:
            raise ProviderError(str(exc), provider=self.name, retryable=True) from exc

    async def embed(self, request: EmbedRequest) -> EmbedResponse:
        model = request.model or self.embed_model
        data = await self._post(
            "/embeddings", {"model": model, "input": list(request.texts)}
        )
        vectors = [
            item["embedding"] for item in sorted(data["data"], key=lambda d: d["index"])
        ]
        return EmbedResponse(
            vectors=vectors,
            model=model,
            dimensions=len(vectors[0]) if vectors else 0,
            usage=Usage(prompt_tokens=data.get("usage", {}).get("prompt_tokens", 0)),
        )

    async def structured(self, request: StructuredRequest) -> dict[str, Any]:
        data = await self._post(
            "/chat/completions",
            {
                "model": request.model or self.model,
                "messages": [
                    {"role": m.role.value, "content": m.content} for m in request.messages
                ],
                "temperature": 0.0,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "result",
                        "strict": True,
                        "schema": strict_schema(request.json_schema),
                    },
                },
            },
        )
        content = data["choices"][0]["message"].get("content") or "{}"
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ProviderError(
                "structured response was not valid JSON",
                provider=self.name,
                retryable=True,
            ) from exc
        return dict(without_nulls(parsed))

    async def health(self) -> HealthReport:
        started = time.perf_counter()
        try:
            response = await self._client.get("/models", timeout=10.0)
            await self._raise_for_status(response)
        except (httpx.HTTPError, ProviderError) as exc:
            return HealthReport(healthy=False, detail=str(exc))
        return HealthReport(
            healthy=True, latency_ms=(time.perf_counter() - started) * 1000
        )

    def _payload(self, request: ChatRequest, *, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model or self.model,
            "messages": [
                {"role": m.role.value, "content": m.content} for m in request.messages
            ],
            "temperature": request.temperature,
            "stream": stream,
        }
        if request.max_tokens:
            payload["max_completion_tokens"] = request.max_tokens
        if request.stop:
            payload["stop"] = list(request.stop)
        return payload

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
        # A non-2xx response from client.stream() hasn't been read yet -- the
        # error body is a small plain JSON object even when stream=true was
        # requested. aread() is a safe no-op for a response already read by
        # client.post()/_post(), so this is correct regardless of call site.
        await response.aread()

        error_type: str | None = None
        error_message: str | None = None
        try:
            body = response.json()
            error = body.get("error") if isinstance(body, dict) else None
            if isinstance(error, dict):
                error_type = error.get("type")
                error_message = error.get("message")
        except (json.JSONDecodeError, ValueError):
            pass
        detail = error_message or response.text[:MAX_ERROR_DETAIL_CHARS]

        # The one place this ever gets logged, regardless of which call site
        # (chat/stream/structured/health) triggered it -- an OpenAI error body
        # has no secrets in it, so this is safe to log in full.
        log.warning(
            "openai.error_response",
            status=status,
            error_type=error_type,
            error_message=error_message,
        )

        raise ProviderError(
            f"OpenAI returned {status}: {detail}"
            if detail
            else f"OpenAI returned {status}",
            provider=self.name,
            retryable=status == 429 or status >= 500,
            status=status,
        )


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """The same schema in the shape OpenAI's strict mode accepts.

    Strict structured outputs refuse any object without
    `additionalProperties: false`, and want every property listed in
    `required`. NOEMA's schemas were written for the other providers, which
    accept optional fields, so every structured call routed here failed with
    a 400 (goal parsing, curriculum, intent, the guard...). Here each object
    is closed, and a field that was optional becomes required-but-nullable;
    `without_nulls` then drops those nulls from the answer, so callers see
    the same shape as before.
    """
    return cast(dict[str, Any], _strict(copy.deepcopy(schema)))


def _strict(node: Any) -> Any:
    if isinstance(node, list):
        return [_strict(item) for item in node]
    if not isinstance(node, dict):
        return node
    for key in ("items", "anyOf", "oneOf", "allOf"):
        if key in node:
            node[key] = _strict(node[key])
    for key in ("$defs", "definitions"):
        if isinstance(node.get(key), dict):
            node[key] = {name: _strict(sub) for name, sub in node[key].items()}
    properties = node.get("properties")
    if isinstance(properties, dict):
        required = set(node.get("required", []))
        for name, sub in properties.items():
            sub = _strict(sub)
            properties[name] = sub if name in required else _nullable(sub)
        node["required"] = list(properties)
        node["additionalProperties"] = False
    elif node.get("type") == "object":
        node.setdefault("properties", {})
        node["required"] = []
        node["additionalProperties"] = False
    return node


def _nullable(node: dict[str, Any]) -> dict[str, Any]:
    kind = node.get("type")
    if isinstance(kind, str):
        node["type"] = [kind, "null"]
    elif isinstance(kind, list) and "null" not in kind:
        node["type"] = [*kind, "null"]
    elif kind is None:
        return {"anyOf": [node, {"type": "null"}]}
    if "enum" in node and None not in node["enum"]:
        node["enum"] = [*node["enum"], None]
    return node


def without_nulls(value: Any) -> Any:
    """Drop the nulls strict mode put where a field was simply absent."""
    if isinstance(value, dict):
        return {k: without_nulls(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [without_nulls(item) for item in value]
    return value
