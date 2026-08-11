"""The ingestion pipeline.

Stages run in order, each recording its status on the source row so a failure names
the stage it happened in rather than "ingestion failed". Stages are separately
retryable: a failure at embedding must never force a re-parse of a 400-page PDF.

    parse → chunk → embed → index

Concept extraction and the knowledge graph are the next slice; the source reaches
``ready`` after indexing so a notebook is searchable without waiting for them.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.config import Settings
from noema.core.logging import get_logger
from noema.db.models import Chunk as ChunkRow
from noema.db.models import Source, SourceStatus
from noema.ingestion import parsers
from noema.ingestion.chunking import Chunk, ChunkSettings, chunk_document
from noema.ingestion.ir import ParsedDocument
from noema.ingestion.storage import Storage
from noema.providers.base import EmbedRequest
from noema.providers.gateway import AIGateway

log = get_logger(__name__)

__all__ = ["IngestionResult", "ingest_source"]

#: Embedding in batches keeps the request count sane on a 600-chunk textbook without
#: building a payload big enough to be rejected.
EMBED_BATCH = 32


@dataclass(frozen=True, slots=True)
class IngestionResult:
    source_id: uuid.UUID
    chunk_count: int
    page_count: int | None
    embedded: bool


async def ingest_source(
    session: AsyncSession,
    source_id: uuid.UUID,
    *,
    storage: Storage,
    gateway: AIGateway | None,
    settings: Settings,
) -> IngestionResult:
    """Run the full pipeline for one source, recording progress as it goes."""
    source = await session.get(Source, source_id)
    if source is None:
        raise ValueError(f"source {source_id} does not exist")

    try:
        document = await _parse(session, source, storage)
        chunks = await _chunk(session, source, document)
        embedded = await _embed_and_index(session, source, chunks, gateway, settings)
    except Exception as exc:
        await _fail(session, source, exc)
        raise

    await _set_status(session, source, SourceStatus.READY)
    log.info(
        "ingestion.complete",
        source_id=str(source_id),
        chunks=len(chunks),
        embedded=embedded,
    )
    return IngestionResult(
        source_id=source_id,
        chunk_count=len(chunks),
        page_count=document.page_count,
        embedded=embedded,
    )


async def _parse(
    session: AsyncSession, source: Source, storage: Storage
) -> ParsedDocument:
    await _set_status(session, source, SourceStatus.PARSING)

    if source.storage_key is None:
        raise ValueError("source has no stored file")

    data = await storage.get(source.storage_key)
    document = parsers.parse_source(
        source.kind, data, url=source.source_metadata.get("url")
    )

    if document.is_empty:
        raise parsers.ParseFailed(
            "No text could be extracted. If this is a scanned document, OCR either "
            "is not installed or could not read it."
        )

    source.page_count = document.page_count
    source.source_metadata = {**source.source_metadata, **document.metadata}
    await session.flush()
    return document


async def _chunk(
    session: AsyncSession, source: Source, document: ParsedDocument
) -> list[Chunk]:
    await _set_status(session, source, SourceStatus.CHUNKING)

    chunks = chunk_document(document, ChunkSettings())
    if not chunks:
        raise parsers.ParseFailed("This document produced no usable text.")

    # Re-ingesting replaces chunks rather than appending; the stage is idempotent.
    await session.execute(delete(ChunkRow).where(ChunkRow.source_id == source.id))

    for chunk in chunks:
        session.add(
            ChunkRow(
                owner_id=source.owner_id,
                source_id=source.id,
                notebook_id=source.notebook_id,
                ordinal=chunk.ordinal,
                content=chunk.content,
                token_count=chunk.token_count,
                heading_path=chunk.heading_path,
                page_from=chunk.page_from,
                page_to=chunk.page_to,
            )
        )
    await session.flush()
    return chunks


async def _embed_and_index(
    session: AsyncSession,
    source: Source,
    chunks: Sequence[Chunk],
    gateway: AIGateway | None,
    settings: Settings,
) -> bool:
    """Embed every chunk, or leave them searchable by text alone.

    A notebook without embeddings still works — full-text search covers it — so an
    unavailable embedding model degrades the feature rather than failing the upload.
    """
    if gateway is None:
        log.warning("ingestion.embedding_skipped", source_id=str(source.id))
        return False

    await _set_status(session, source, SourceStatus.EMBEDDING)

    rows = (
        await session.scalars(
            select(ChunkRow)
            .where(ChunkRow.source_id == source.id)
            .order_by(ChunkRow.ordinal)
        )
    ).all()

    for start in range(0, len(rows), EMBED_BATCH):
        batch = rows[start : start + EMBED_BATCH]
        texts = [chunks[row.ordinal].embedding_text() for row in batch]

        response = await gateway.embed(
            EmbedRequest(texts=texts, model=settings.noema_embedding_model)
        )

        if response.dimensions != settings.noema_embedding_dim:
            raise ValueError(
                f"{response.model} returns {response.dimensions}-dimensional vectors "
                f"but this deployment is configured for {settings.noema_embedding_dim}. "
                "Set NOEMA_EMBEDDING_DIM to match and re-embed."
            )

        for row, vector in zip(batch, response.vectors, strict=True):
            row.embedding = list(vector)
            row.embedding_model = response.model

    await session.flush()
    return True


async def _set_status(
    session: AsyncSession, source: Source, status: SourceStatus
) -> None:
    source.status = status
    source.error = None
    await session.flush()


async def _fail(session: AsyncSession, source: Source, exc: Exception) -> None:
    """Record the failure against the stage it happened in.

    The message is shown to the user, so it names what to do rather than what broke
    internally.
    """
    source.error = {
        "stage": source.status.value,
        "type": type(exc).__name__,
        "detail": str(exc)[:500],
    }
    source.status = SourceStatus.FAILED
    await session.flush()
    log.warning(
        "ingestion.failed",
        source_id=str(source.id),
        stage=source.error["stage"],
        error=type(exc).__name__,
    )
