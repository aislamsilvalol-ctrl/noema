"""Embedding cache.

Ingesting a 300-page textbook is roughly 600 chunks and 600 embedding calls.
Re-ingesting it after a chunking change pays for all of them again, and under BYOK
that is the user's money. The same text through the same model always produces the
same vector, so paying twice is not a trade-off — it is waste.

Keyed on ``sha256(text)`` and the model name. Vectors are stored as float32, which
is not a lossy shortcut: ``pgvector``'s column type is float4, so this is exactly
the precision the database was going to keep anyway.

A miss, a broken connection or a disabled cache all behave the same way — call the
provider. Nothing here may turn a Redis problem into a failed ingestion.

One honest caveat: the keyspace is per deployment, not per user, because a vector
does not belong to anyone. On a shared instance that makes the cache a very weak
oracle for "has anyone else ingested this exact text", observable only as latency.
Set ``NOEMA_EMBEDDING_CACHE_TTL_DAYS=0`` if that matters more than the bill.
"""

from __future__ import annotations

import hashlib
from array import array
from collections.abc import Awaitable, Callable, Sequence

from redis.asyncio import Redis
from redis.exceptions import RedisError

from noema.core.logging import get_logger
from noema.providers.base import EmbedResponse, Usage

log = get_logger(__name__)

__all__ = ["EmbeddingCache"]

PREFIX = "noema:emb"


class EmbeddingCache:
    def __init__(self, redis: Redis | None, *, ttl_days: int = 30) -> None:
        #: A cache that is off and a cache that is unreachable take the same path,
        #: so there is only one behaviour to reason about.
        self._redis = redis if ttl_days > 0 else None
        self._ttl = ttl_days * 24 * 60 * 60

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str,
        fetch: Callable[[Sequence[str]], Awaitable[EmbedResponse]],
    ) -> EmbedResponse:
        """Embed ``texts``, paying only for the ones not already known.

        The response is assembled in input order regardless of how much of it came
        from the cache, so callers cannot tell the difference — except in the usage
        figures, which report only what was actually spent.
        """
        if not texts:
            return EmbedResponse(vectors=[], model=model, dimensions=0, usage=Usage())

        keys = [_key(text, model) for text in texts]
        cached = await self._get_many(keys)

        # Deduplicated: a document with repeated boilerplate should pay once, and
        # sending the same string twice in one batch is pure waste.
        missing: list[str] = []
        seen: set[str] = set()
        for text, key in zip(texts, keys, strict=True):
            if key not in cached and key not in seen:
                seen.add(key)
                missing.append(text)

        fresh: dict[str, Sequence[float]] = {}
        response: EmbedResponse | None = None
        if missing:
            response = await fetch(missing)
            for text, vector in zip(missing, response.vectors, strict=True):
                fresh[_key(text, model)] = vector
            await self._put_many(fresh)

        # Membership, not truthiness: a zero vector is falsy, and `or` would send
        # it to `fresh`, which does not have it — a KeyError on a legal value.
        vectors = [cached[key] if key in cached else fresh[key] for key in keys]
        dimensions = response.dimensions if response else len(vectors[0])

        if cached:
            log.info(
                "embeddings.cache",
                hits=len(texts) - len(missing),
                calls=len(missing),
                model=model,
            )

        return EmbedResponse(
            vectors=vectors,
            model=response.model if response else model,
            dimensions=dimensions,
            # Only what was actually spent. Reporting the full batch would make the
            # usage log a record of what the user was nearly charged.
            usage=response.usage if response else Usage(),
        )

    async def _get_many(self, keys: Sequence[str]) -> dict[str, Sequence[float]]:
        if self._redis is None or not keys:
            return {}
        try:
            raw = await self._redis.mget(list(dict.fromkeys(keys)))
        except RedisError as exc:
            log.warning("embeddings.cache_unavailable", error=str(exc))
            return {}

        out: dict[str, Sequence[float]] = {}
        for key, blob in zip(dict.fromkeys(keys), raw, strict=True):
            if not blob:
                continue
            if not isinstance(blob, bytes):
                # A client built with decode_responses=True hands back str, and
                # float32 bytes do not survive being decoded as text. Treat it as a
                # miss and pay for the embedding rather than return a corrupt
                # vector, which nothing downstream could detect.
                log.warning("embeddings.cache_not_binary", key=key)
                continue
            out[key] = _decode(blob)
        return out

    async def _put_many(self, vectors: dict[str, Sequence[float]]) -> None:
        if self._redis is None or not vectors:
            return
        try:
            async with self._redis.pipeline(transaction=False) as pipe:
                for key, vector in vectors.items():
                    pipe.set(key, _encode(vector), ex=self._ttl)
                await pipe.execute()
        except RedisError as exc:
            # The vectors are already computed and on their way to Postgres. Failing
            # here would throw away work that has been paid for.
            log.warning("embeddings.cache_write_failed", error=str(exc))


def _key(text: str, model: str) -> str:
    return f"{PREFIX}:{model}:{hashlib.sha256(text.encode()).hexdigest()}"


def _encode(vector: Sequence[float]) -> bytes:
    return array("f", vector).tobytes()


def _decode(blob: bytes) -> Sequence[float]:
    out = array("f")
    out.frombytes(blob)
    return out.tolist()
