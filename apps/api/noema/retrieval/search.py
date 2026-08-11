"""Hybrid retrieval over a user's chunks.

Dense search alone is unreliable on notation, proper nouns and exact terms —
precisely what academic material is full of. Sparse search alone misses paraphrase.
Running both and fusing on rank is the cheapest way to be bad at neither.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from noema.core.logging import get_logger
from noema.db.models import Chunk, Source
from noema.providers.base import EmbedRequest, ProviderError
from noema.providers.gateway import AIGateway
from noema.retrieval.fusion import Ranked, fuse, max_possible_score

log = get_logger(__name__)

__all__ = ["RetrievalSettings", "Retrieved", "retrieve"]

#: Postgres text search configuration. 'simple' does no stemming, which is the right
#: call for an unknown mix of languages — the dense side carries semantics anyway.
TS_CONFIG = "simple"


@dataclass(frozen=True, slots=True)
class RetrievalSettings:
    candidates: int = 40  # per retriever, before fusion
    top_k: int = 8  # after fusion, into the prompt
    min_score: float = 0.35  # fused; below this we say we could not find it

    #: Absolute cosine-similarity floor on the dense side, applied *before* fusion.
    #:
    #: This is load-bearing. RRF fuses on rank, and a rank always exists — a vector
    #: search asked about photosynthesis over a notebook of optimisation notes still
    #: returns its nearest forty chunks, and fusion would rank one of them first.
    #: Without an absolute floor there is no such thing as "nothing relevant here",
    #: and the refusal the whole trust model depends on could never fire.
    min_similarity: float = 0.35

    def __post_init__(self) -> None:
        if self.top_k > self.candidates:
            raise ValueError("top_k cannot exceed the candidate pool")
        if not 0 <= self.min_score <= 1:
            raise ValueError("min_score must be in [0, 1]")
        if not 0 <= self.min_similarity <= 1:
            raise ValueError("min_similarity must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class Retrieved:
    """A chunk that survived fusion, with everything a citation needs."""

    chunk_id: uuid.UUID
    source_id: uuid.UUID
    content: str
    heading_path: list[str]
    page_from: int | None
    page_to: int | None
    source_title: str
    score: float
    found_by_both: bool

    @property
    def location(self) -> str:
        """Human-readable position, for the citation the user actually sees."""
        parts = [self.source_title]
        if self.page_from:
            pages = (
                f"p. {self.page_from}"
                if self.page_to in (None, self.page_from)
                # En dash: this string is shown to the user, and a page range is
                # one of the few places typography is not decoration.
                else f"pp. {self.page_from}\u2013{self.page_to}"
            )
            parts.append(pages)
        if self.heading_path:
            parts.append(" > ".join(self.heading_path))
        return " · ".join(parts)


async def retrieve(
    session: AsyncSession,
    query: str,
    *,
    owner_id: uuid.UUID,
    notebook_id: uuid.UUID | None = None,
    gateway: AIGateway | None = None,
    embedding_model: str | None = None,
    settings: RetrievalSettings | None = None,
) -> list[Retrieved]:
    """Retrieve the chunks most likely to answer ``query``.

    Falls back to text-only search when embeddings are unavailable — a notebook
    ingested without a reachable embedding provider is still searchable.
    """
    settings = settings or RetrievalSettings()
    if not query.strip():
        return []

    sparse_ids = await _sparse(session, query, owner_id, notebook_id, settings.candidates)
    dense_ids = await _dense(
        session, query, owner_id, notebook_id, settings, gateway, embedding_model
    )

    if not dense_ids and not sparse_ids:
        return []

    ranked = fuse(dense_ids, sparse_ids, limit=settings.top_k)
    return await _hydrate(session, ranked, owner_id, settings)


async def _dense(
    session: AsyncSession,
    query: str,
    owner_id: uuid.UUID,
    notebook_id: uuid.UUID | None,
    settings: RetrievalSettings,
    gateway: AIGateway | None,
    embedding_model: str | None,
) -> list[uuid.UUID]:
    if gateway is None:
        return []

    try:
        response = await gateway.embed(EmbedRequest(texts=[query], model=embedding_model))
    except ProviderError as exc:
        # Text search still works, so a down embedding provider narrows results
        # rather than breaking search entirely.
        log.warning("retrieval.dense_unavailable", error=str(exc), provider=exc.provider)
        return []

    vector = list(response.vectors[0])
    distance = Chunk.embedding.cosine_distance(vector)

    stmt = (
        _scoped(select(Chunk.id), owner_id, notebook_id)
        .where(
            Chunk.embedding.is_not(None),
            # cosine distance = 1 - similarity, so the floor becomes a ceiling here.
            distance <= 1 - settings.min_similarity,
        )
        .order_by(distance)
        .limit(settings.candidates)
    )
    return list((await session.scalars(stmt)).all())


async def _sparse(
    session: AsyncSession,
    query: str,
    owner_id: uuid.UUID,
    notebook_id: uuid.UUID | None,
    candidates: int,
) -> list[uuid.UUID]:
    tsquery = _tsquery(query)
    if tsquery is None:
        return []

    rank = func.ts_rank_cd(Chunk.tsv, tsquery)

    stmt = (
        _scoped(select(Chunk.id), owner_id, notebook_id)
        .where(Chunk.tsv.op("@@")(tsquery))
        .order_by(rank.desc())
        .limit(candidates)
    )
    return list((await session.scalars(stmt)).all())


async def _hydrate(
    session: AsyncSession,
    ranked: Sequence[Ranked],
    owner_id: uuid.UUID,
    settings: RetrievalSettings,
) -> list[Retrieved]:
    if not ranked:
        return []

    ids = [r.chunk_id for r in ranked]
    rows = (
        await session.execute(
            select(Chunk, Source.original_filename, Source.source_metadata)
            .join(Source, Source.id == Chunk.source_id)
            .where(Chunk.id.in_(ids), Chunk.owner_id == owner_id)
        )
    ).all()

    by_id = {row[0].id: row for row in rows}
    ceiling = max_possible_score()

    results: list[Retrieved] = []
    for entry in ranked:
        row = by_id.get(entry.chunk_id)
        if row is None:
            continue
        chunk, filename, metadata = row
        title = (metadata or {}).get("title") or filename or "Untitled source"

        results.append(
            Retrieved(
                chunk_id=chunk.id,
                source_id=chunk.source_id,
                content=chunk.content,
                heading_path=list(chunk.heading_path or []),
                page_from=chunk.page_from,
                page_to=chunk.page_to,
                source_title=str(title),
                score=min(entry.score / ceiling, 1.0),
                found_by_both=entry.found_by_both,
            )
        )

    # Everything below threshold means we found nothing worth answering from, and
    # returning the best of a bad set is how a tutor ends up confidently citing an
    # irrelevant paragraph. The caller says so instead.
    return [r for r in results if r.score >= settings.min_score]


WORD = re.compile(r"\w+", re.UNICODE)

#: Single letters and digits match everything and rank nothing.
MIN_TERM_LENGTH = 2


def _tsquery(query: str) -> ColumnElement[Any] | None:
    """Build an OR query with prefix matching, rather than ANDing every word.

    `plainto_tsquery` ANDs its terms, so a natural question — "how does gradient
    descent converge" — matches only a chunk containing *every* word including the
    filler, which is essentially never. Prefix matching then covers the inflection
    the 'simple' configuration deliberately does not stem: `converge:*` finds
    "converges" without committing the index to one language.

    Ranking, not matching, decides relevance: `ts_rank_cd` scores a chunk hitting
    four of the terms above one hitting a single term.
    """
    terms = [term.lower() for term in WORD.findall(query) if len(term) >= MIN_TERM_LENGTH]
    if not terms:
        return None

    tsquery: ColumnElement[Any] | None = None
    for term in terms:
        # Parameterised per term, so the user's text never reaches tsquery syntax.
        clause: ColumnElement[Any] = func.to_tsquery(TS_CONFIG, term + ":*")
        tsquery = clause if tsquery is None else tsquery.op("||")(clause)
    return tsquery


def _scoped(
    stmt: Select[tuple[uuid.UUID]],
    owner_id: uuid.UUID,
    notebook_id: uuid.UUID | None,
) -> Select[tuple[uuid.UUID]]:
    """Scope every retrieval query by owner, and by notebook when asked.

    Notebook scoping is the feature, not a filter: "explain this using my materials"
    has to mean the materials in front of the user.
    """
    stmt = stmt.where(Chunk.owner_id == owner_id)
    if notebook_id is not None:
        stmt = stmt.where(Chunk.notebook_id == notebook_id)
    return stmt
