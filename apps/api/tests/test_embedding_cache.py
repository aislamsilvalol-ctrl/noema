"""The embedding cache.

What matters here is not that Redis stores bytes. It is that the caller cannot tell
a hit from a miss except in the bill: same vectors, same order, same dimensions —
and no second call for text already known.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

import pytest
from redis.asyncio import Redis

from noema.providers.base import EmbedResponse, Usage
from noema.providers.cache import EmbeddingCache

pytestmark = pytest.mark.asyncio


class Embedder:
    """A provider that counts what it was actually asked to do."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def __call__(self, texts: Sequence[str]) -> EmbedResponse:
        self.calls.append(list(texts))
        return EmbedResponse(
            # Deterministic and text-dependent, so a wrong-order bug is visible.
            vectors=[[float(len(t)), float(sum(t.encode()) % 97), 0.5] for t in texts],
            model="test-embed",
            dimensions=3,
            usage=Usage(prompt_tokens=len(texts), completion_tokens=0),
        )

    @property
    def texts_sent(self) -> list[str]:
        return [text for call in self.calls for text in call]


@pytest.fixture
def cache(redis: Any) -> EmbeddingCache:
    return EmbeddingCache(redis, ttl_days=1)


@pytest.fixture
def model() -> str:
    # Per-test model name, so tests never share a keyspace.
    return f"test-{uuid.uuid4().hex[:8]}"


async def test_a_second_pass_over_the_same_text_costs_nothing(
    cache: EmbeddingCache, model: str
) -> None:
    """The whole point: re-ingesting a textbook must not buy it again."""
    embedder = Embedder()
    texts = ["the chain rule", "gradient descent", "a loss function"]

    first = await cache.embed(texts, model=model, fetch=embedder)
    second = await cache.embed(texts, model=model, fetch=embedder)

    assert len(embedder.calls) == 1, "the second pass called the provider"
    assert [list(v) for v in second.vectors] == [list(v) for v in first.vectors]
    assert second.dimensions == first.dimensions
    assert second.usage.prompt_tokens == 0, "a cached batch reported spend"


async def test_a_partial_hit_pays_only_for_what_is_new(
    cache: EmbeddingCache, model: str
) -> None:
    """And the result still comes back in the caller's order.

    Reassembling hits and misses is where an off-by-one silently attaches the
    wrong vector to the wrong chunk — which no downstream check would catch.
    """
    embedder = Embedder()
    await cache.embed(["known"], model=model, fetch=embedder)

    texts = ["new one", "known", "new two"]
    response = await cache.embed(texts, model=model, fetch=embedder)

    assert embedder.calls[1] == ["new one", "new two"]

    direct = Embedder()
    expected = await direct(texts)
    assert [list(v) for v in response.vectors] == [list(v) for v in expected.vectors]


async def test_repeated_text_in_one_batch_is_embedded_once(
    cache: EmbeddingCache, model: str
) -> None:
    """Boilerplate repeats across a document; it should cost once."""
    embedder = Embedder()
    texts = ["heading", "body", "heading", "heading"]

    response = await cache.embed(texts, model=model, fetch=embedder)

    assert embedder.texts_sent == ["heading", "body"]
    assert list(response.vectors[0]) == list(response.vectors[2])
    assert len(response.vectors) == 4


async def test_the_model_is_part_of_the_key(cache: EmbeddingCache, model: str) -> None:
    """Two models do not produce the same vector, and must not share an entry."""
    embedder = Embedder()

    await cache.embed(["shared text"], model=model, fetch=embedder)
    await cache.embed(["shared text"], model=f"{model}-large", fetch=embedder)

    assert len(embedder.calls) == 2


async def test_float32_is_close_enough_to_be_the_same_vector(
    cache: EmbeddingCache, model: str
) -> None:
    """Stored as float32 because pgvector's column is float4.

    The round trip has to be lossless at that precision, or a cached vector would
    rank differently from a fresh one.
    """
    embedder = Embedder()

    fresh = await cache.embed(["precision"], model=model, fetch=embedder)
    cached = await cache.embed(["precision"], model=model, fetch=embedder)

    assert list(cached.vectors[0]) == pytest.approx(list(fresh.vectors[0]), rel=1e-6)


async def test_a_disabled_cache_still_embeds(model: str) -> None:
    """TTL 0 means off, not broken."""
    embedder = Embedder()
    off = EmbeddingCache(None, ttl_days=0)

    first = await off.embed(["text"], model=model, fetch=embedder)
    second = await off.embed(["text"], model=model, fetch=embedder)

    assert len(embedder.calls) == 2
    assert list(first.vectors[0]) == list(second.vectors[0])


async def test_redis_being_down_does_not_stop_ingestion(model: str) -> None:
    """Port 1 is reserved and never listening, so this fails to connect."""
    embedder = Embedder()
    broken = EmbeddingCache(Redis.from_url("redis://127.0.0.1:1/0"), ttl_days=1)

    response = await broken.embed(["text"], model=model, fetch=embedder)

    assert len(response.vectors) == 1
    assert embedder.calls == [["text"]]
