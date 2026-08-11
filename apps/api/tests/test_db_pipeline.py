"""The ingestion pipeline end to end against a real database.

Runs the whole thing — parse, chunk, embed, index — with the deterministic provider,
so the vector column, the batching and the failure recording are all exercised
rather than mocked.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.config import Settings
from noema.db.models import (
    Chunk,
    Notebook,
    Source,
    SourceKind,
    SourceStatus,
    Subject,
    User,
    Workspace,
)
from noema.db.repository import OwnedRepository
from noema.ingestion.pipeline import ingest_source
from noema.ingestion.storage import LocalStorage, storage_key
from noema.providers.gateway import AIGateway
from noema.providers.mock import MockProvider

DOCUMENT = b"""# Optimization

Gradient descent minimises a loss function by stepping downhill.

## Convergence

It converges when the step size is small enough relative to the curvature.
The proof depends on the function being convex and the gradient being Lipschitz.

## Momentum

Momentum accumulates a velocity term across steps, which damps oscillation in
narrow valleys and speeds up progress along shallow directions.
"""


@pytest.fixture
async def notebook(db: AsyncSession, user: User) -> Notebook:
    workspace = await OwnedRepository(db, Workspace, user.id).create(
        title="CS", slug=f"cs-{uuid.uuid4().hex[:8]}"
    )
    subject = await OwnedRepository(db, Subject, user.id).create(
        workspace_id=workspace.id, title="ML", slug="ml"
    )
    return await OwnedRepository(db, Notebook, user.id).create(
        subject_id=subject.id, title="Optimization", slug="opt", retrieval_settings={}
    )


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(str(tmp_path))


async def make_source(
    db: AsyncSession,
    user: User,
    notebook: Notebook,
    storage: LocalStorage,
    data: bytes = DOCUMENT,
    kind: SourceKind = SourceKind.MD,
) -> Source:
    source = await OwnedRepository(db, Source, user.id).create(
        notebook_id=notebook.id,
        kind=kind,
        original_filename="optimization.md",
        byte_size=len(data),
        status=SourceStatus.PENDING,
        source_metadata={},
    )
    key = storage_key(user.id, source.id, kind.value)
    await storage.put(key, data)
    source.storage_key = key
    await db.flush()
    return source


async def test_a_markdown_source_becomes_embedded_chunks(
    db: AsyncSession,
    user: User,
    notebook: Notebook,
    storage: LocalStorage,
    settings: Settings,
) -> None:
    source = await make_source(db, user, notebook, storage)
    gateway = AIGateway(MockProvider(dimensions=settings.noema_embedding_dim))

    result = await ingest_source(
        db, source.id, storage=storage, gateway=gateway, settings=settings
    )

    assert result.chunk_count > 0
    assert result.embedded

    await db.refresh(source)
    assert source.status is SourceStatus.READY
    assert source.error is None

    chunks = (
        await db.scalars(
            select(Chunk).where(Chunk.source_id == source.id).order_by(Chunk.ordinal)
        )
    ).all()

    assert len(chunks) == result.chunk_count
    assert all(chunk.owner_id == user.id for chunk in chunks)
    for chunk in chunks:
        assert chunk.embedding is not None
        assert len(chunk.embedding) == settings.noema_embedding_dim


async def test_heading_paths_and_content_survive_into_the_database(
    db: AsyncSession,
    user: User,
    notebook: Notebook,
    storage: LocalStorage,
    settings: Settings,
) -> None:
    source = await make_source(db, user, notebook, storage)
    await ingest_source(
        db,
        source.id,
        storage=storage,
        gateway=AIGateway(MockProvider(dimensions=settings.noema_embedding_dim)),
        settings=settings,
    )

    chunks = (
        await db.scalars(
            select(Chunk).where(Chunk.source_id == source.id).order_by(Chunk.ordinal)
        )
    ).all()

    paths = [chunk.heading_path for chunk in chunks]
    assert ["Optimization", "Convergence"] in paths

    convergence = next(c for c in chunks if c.heading_path[-1:] == ["Convergence"])
    # The stored content is the source text, without our retrieval scaffolding.
    assert "converges when the step size" in convergence.content
    assert not convergence.content.startswith("Optimization >")


async def test_the_generated_search_vector_is_populated_by_postgres(
    db: AsyncSession,
    user: User,
    notebook: Notebook,
    storage: LocalStorage,
    settings: Settings,
) -> None:
    """`tsv` is a generated column, so hybrid search works without an extra write."""
    source = await make_source(db, user, notebook, storage)
    await ingest_source(
        db,
        source.id,
        storage=storage,
        gateway=AIGateway(MockProvider(dimensions=settings.noema_embedding_dim)),
        settings=settings,
    )

    tsv = await db.scalar(select(Chunk.tsv).where(Chunk.source_id == source.id).limit(1))
    assert tsv is not None and tsv != ""


async def test_re_ingesting_replaces_chunks_rather_than_duplicating_them(
    db: AsyncSession,
    user: User,
    notebook: Notebook,
    storage: LocalStorage,
    settings: Settings,
) -> None:
    source = await make_source(db, user, notebook, storage)
    gateway = AIGateway(MockProvider(dimensions=settings.noema_embedding_dim))

    first = await ingest_source(
        db, source.id, storage=storage, gateway=gateway, settings=settings
    )
    second = await ingest_source(
        db, source.id, storage=storage, gateway=gateway, settings=settings
    )

    assert first.chunk_count == second.chunk_count
    total = (await db.scalars(select(Chunk).where(Chunk.source_id == source.id))).all()
    assert len(total) == second.chunk_count


async def test_ingestion_without_an_embedding_provider_still_indexes_text(
    db: AsyncSession,
    user: User,
    notebook: Notebook,
    storage: LocalStorage,
    settings: Settings,
) -> None:
    """No embeddings degrades to text search rather than failing the upload."""
    source = await make_source(db, user, notebook, storage)

    result = await ingest_source(
        db, source.id, storage=storage, gateway=None, settings=settings
    )

    assert result.chunk_count > 0
    assert not result.embedded
    await db.refresh(source)
    assert source.status is SourceStatus.READY

    chunks = (await db.scalars(select(Chunk).where(Chunk.source_id == source.id))).all()
    assert all(chunk.embedding is None for chunk in chunks)


async def test_a_failure_records_the_stage_it_happened_in(
    db: AsyncSession,
    user: User,
    notebook: Notebook,
    storage: LocalStorage,
    settings: Settings,
) -> None:
    """ "Ingestion failed" is useless; the user needs to know what to fix."""
    source = await make_source(db, user, notebook, storage, data=b"   \n\n   ")

    with pytest.raises(Exception):  # noqa: B017 — any parser failure is in scope
        await ingest_source(
            db, source.id, storage=storage, gateway=None, settings=settings
        )

    await db.refresh(source)
    assert source.status is SourceStatus.FAILED
    assert source.error is not None
    assert source.error["stage"] == SourceStatus.PARSING.value
    assert "OCR" in source.error["detail"] or "text" in source.error["detail"]


async def test_a_dimension_mismatch_is_refused_rather_than_silently_stored(
    db: AsyncSession,
    user: User,
    notebook: Notebook,
    storage: LocalStorage,
    settings: Settings,
) -> None:
    """Mixing vector widths in one column corrupts search in a way that is hard to see."""
    source = await make_source(db, user, notebook, storage)
    wrong = AIGateway(MockProvider(dimensions=settings.noema_embedding_dim + 8))

    with pytest.raises(ValueError, match="NOEMA_EMBEDDING_DIM"):
        await ingest_source(
            db, source.id, storage=storage, gateway=wrong, settings=settings
        )

    await db.refresh(source)
    assert source.status is SourceStatus.FAILED
    assert source.error is not None
    assert source.error["stage"] == SourceStatus.EMBEDDING.value


async def test_a_csv_is_summarised_rather_than_split_per_row(
    db: AsyncSession,
    user: User,
    notebook: Notebook,
    storage: LocalStorage,
    settings: Settings,
) -> None:
    rows = "\n".join(f"{i},concept-{i}" for i in range(2000))
    source = await make_source(
        db, user, notebook, storage, data=f"id,name\n{rows}".encode(), kind=SourceKind.CSV
    )

    result = await ingest_source(
        db,
        source.id,
        storage=storage,
        gateway=AIGateway(MockProvider(dimensions=settings.noema_embedding_dim)),
        settings=settings,
    )

    # 2000 rows must not become 2000 near-identical vectors.
    assert result.chunk_count < 20
