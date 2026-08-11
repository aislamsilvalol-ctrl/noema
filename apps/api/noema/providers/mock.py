"""Deterministic provider for tests, CI and offline development.

Real providers are non-deterministic and cost money; neither belongs in a test suite.
Every response here is a pure function of the request, so prompt and pipeline changes
produce reviewable diffs.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import AsyncIterator
from typing import Any

from noema.providers.base import (
    Capabilities,
    ChatRequest,
    ChatResponse,
    EmbedRequest,
    EmbedResponse,
    HealthReport,
    StreamEvent,
    StructuredRequest,
    Usage,
)
from noema.providers.registry import register

WORD = re.compile(r"\w+", re.UNICODE)


@register("mock")
class MockProvider:
    name = "mock"
    capabilities = Capabilities(
        chat=True,
        streaming=True,
        embeddings=True,
        structured_output="native",
        max_context=32_000,
        max_output=4_096,
    )

    def __init__(self, dimensions: int = 768, fail: bool = False) -> None:
        self.dimensions = dimensions
        self.fail = fail
        self.calls: list[str] = []

    async def chat(self, request: ChatRequest) -> ChatResponse:
        self.calls.append("chat")
        content = self._reply(request)
        return ChatResponse(
            content=content,
            model=request.model or "mock-1",
            usage=Usage(
                prompt_tokens=sum(len(m.content) // 4 for m in request.messages),
                completion_tokens=len(content) // 4,
            ),
        )

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        self.calls.append("stream")
        response = await self.chat(request)
        for word in response.content.split(" "):
            yield StreamEvent(delta=word + " ")
        yield StreamEvent(done=True, usage=response.usage)

    async def embed(self, request: EmbedRequest) -> EmbedResponse:
        self.calls.append("embed")
        return EmbedResponse(
            vectors=[self._vector(text) for text in request.texts],
            model=request.model or "mock-embed",
            dimensions=self.dimensions,
            usage=Usage(prompt_tokens=sum(len(t) // 4 for t in request.texts)),
        )

    async def structured(self, request: StructuredRequest) -> dict[str, Any]:
        self.calls.append("structured")
        skeleton = _skeleton(request.json_schema)
        if not isinstance(skeleton, dict):
            raise TypeError("structured schemas must describe an object")
        return skeleton

    async def health(self) -> HealthReport:
        return HealthReport(healthy=not self.fail, latency_ms=0.0)

    def _reply(self, request: ChatRequest) -> str:
        last = next(
            (m.content for m in reversed(request.messages) if m.role == "user"), ""
        )
        return f"[mock:{request.task.value}] {last[:200]}"

    def _vector(self, text: str) -> list[float]:
        """A hashed bag of words, normalised to unit length.

        Deterministic, like a test double must be — but *also* semantically ordered:
        texts sharing vocabulary land close together and unrelated texts land near
        orthogonal. A double emitting hashed noise would satisfy "same input, same
        vector" while making every similarity threshold, every ranking and every
        refusal untestable, because nothing would ever resemble anything.
        """
        raw = [0.0] * self.dimensions

        for token in WORD.findall(text.lower()):
            digest = hashlib.sha256(token.encode()).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            # A sign bit from the same hash keeps unrelated tokens from piling up
            # in one direction and inflating similarity across the board.
            sign = 1.0 if digest[4] % 2 else -1.0
            raw[bucket] += sign

        norm = math.sqrt(sum(v * v for v in raw))
        if norm == 0:
            # Empty or punctuation-only input: orthogonal to everything, which is
            # the honest answer rather than an arbitrary direction.
            return raw
        return [v / norm for v in raw]


def _skeleton(schema: dict[str, Any]) -> Any:
    """Smallest value satisfying a JSON schema, so structured calls always validate."""
    kind = schema.get("type", "object")
    if kind == "object":
        return {
            name: _skeleton(sub)
            for name, sub in schema.get("properties", {}).items()
            if name in schema.get("required", schema.get("properties", {}))
        }
    if kind == "array":
        return [_skeleton(schema["items"])] if "items" in schema else []
    if kind == "string":
        return schema.get("enum", ["mock"])[0]
    if kind == "integer":
        return schema.get("minimum", 0)
    if kind == "number":
        return float(schema.get("minimum", 0.0))
    if kind == "boolean":
        return False
    return None


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)
