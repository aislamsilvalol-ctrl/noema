"""Source upload, ingestion queueing and deletion, against a real database.

Called directly as plain coroutines, the same convention as the rest of this
suite's `noema.api.v1.*` tests. `check_upload`/`parsers`/`retrieve` are already
covered elsewhere; what's tested here is the route layer's own logic: quota
enforcement, checksum dedup (and its interaction with soft-deletion),
ingestion's idempotency guard, and that a source's file actually goes with it
on delete.
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path

import pytest
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from noema.api.v1.sources import (
    _check_quota,
    delete_source,
    get_source,
    ingestion_events,
    list_sources,
    search,
    start_ingestion,
    upload_source,
)
from noema.core.config import Settings
from noema.core.errors import Conflict, NotFound, QuotaExceeded
from noema.db.base import utcnow
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
from noema.ingestion.storage import LocalStorage, StorageError
from noema.providers.gateway import AIGateway
from noema.providers.mock import MockProvider

pytestmark = pytest.mark.asyncio

MD = b"# Cardiac Cycle\n\nDiastole fills the ventricles with blood.\n"


@pytest.fixture(autouse=True)
def _local_storage(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "storage_local_path", str(tmp_path))


@pytest.fixture
async def notebook(db: AsyncSession, user: User) -> Notebook:
    workspace = await OwnedRepository(db, Workspace, user.id).create(
        title="Bio", slug=f"bio-{uuid.uuid4().hex[:8]}"
    )
    subject = await OwnedRepository(db, Subject, user.id).create(
        workspace_id=workspace.id, title="Cells", slug=f"cells-{uuid.uuid4().hex[:8]}"
    )
    return await OwnedRepository(db, Notebook, user.id).create(
        subject_id=subject.id,
        title="Organelles",
        slug=f"org-{uuid.uuid4().hex[:8]}",
        retrieval_settings={},
    )


def upload_file(data: bytes = MD, filename: str = "notes.md") -> UploadFile:
    return UploadFile(io.BytesIO(data), filename=filename)


# ---------------------------------------------------------------------------
# upload_source
# ---------------------------------------------------------------------------


async def test_upload_stores_the_file_and_creates_a_source(
    db: AsyncSession, user: User, notebook: Notebook, settings: Settings, tmp_path: Path
) -> None:
    out = await upload_source(
        user=user, db=db, settings=settings, notebook_id=notebook.id, file=upload_file()
    )

    assert out.kind is SourceKind.MD
    assert out.byte_size == len(MD)
    assert out.status is SourceStatus.PENDING

    source = await db.get(Source, out.id)
    assert source is not None
    assert source.storage_key is not None
    stored = await LocalStorage(str(tmp_path)).get(source.storage_key)
    assert stored == MD


async def test_upload_to_another_owners_notebook_is_not_found(
    db: AsyncSession, user: User, other_user: User, notebook: Notebook, settings: Settings
) -> None:
    with pytest.raises(NotFound):
        await upload_source(
            user=other_user,
            db=db,
            settings=settings,
            notebook_id=notebook.id,
            file=upload_file(),
        )


async def test_upload_rejects_a_format_this_deployment_cannot_parse(
    db: AsyncSession,
    user: User,
    notebook: Notebook,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from noema.ingestion import parsers

    monkeypatch.setattr(parsers, "available", lambda kind: False)

    with pytest.raises(parsers.ParserUnavailable):
        await upload_source(
            user=user,
            db=db,
            settings=settings,
            notebook_id=notebook.id,
            file=upload_file(),
        )


async def test_upload_enforces_the_storage_quota(
    db: AsyncSession,
    user: User,
    notebook: Notebook,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "noema_user_storage_quota_mb", 0)

    with pytest.raises(QuotaExceeded):
        await upload_source(
            user=user,
            db=db,
            settings=settings,
            notebook_id=notebook.id,
            file=upload_file(),
        )


async def test_reuploading_the_same_file_to_the_same_notebook_is_a_conflict(
    db: AsyncSession, user: User, notebook: Notebook, settings: Settings
) -> None:
    await upload_source(
        user=user, db=db, settings=settings, notebook_id=notebook.id, file=upload_file()
    )

    with pytest.raises(Conflict, match="this notebook"):
        await upload_source(
            user=user,
            db=db,
            settings=settings,
            notebook_id=notebook.id,
            file=upload_file(),
        )


async def test_reuploading_the_same_file_to_another_notebook_names_it(
    db: AsyncSession, user: User, notebook: Notebook, settings: Settings
) -> None:
    other_notebook = await _another_notebook(db, user)
    await upload_source(
        user=user, db=db, settings=settings, notebook_id=notebook.id, file=upload_file()
    )

    with pytest.raises(Conflict, match="another notebook"):
        await upload_source(
            user=user,
            db=db,
            settings=settings,
            notebook_id=other_notebook.id,
            file=upload_file(),
        )


async def test_a_soft_deleted_duplicate_does_not_block_a_reupload(
    db: AsyncSession, user: User, notebook: Notebook, settings: Settings
) -> None:
    first = await upload_source(
        user=user, db=db, settings=settings, notebook_id=notebook.id, file=upload_file()
    )
    row = await db.get(Source, first.id)
    assert row is not None
    row.deleted_at = utcnow()
    await db.flush()

    out = await upload_source(
        user=user, db=db, settings=settings, notebook_id=notebook.id, file=upload_file()
    )

    assert out.id != first.id


async def _another_notebook(db: AsyncSession, user: User) -> Notebook:
    workspace = await OwnedRepository(db, Workspace, user.id).create(
        title="Chemistry", slug=f"chem-{uuid.uuid4().hex[:8]}"
    )
    subject = await OwnedRepository(db, Subject, user.id).create(
        workspace_id=workspace.id, title="Chem", slug=f"chemsub-{uuid.uuid4().hex[:8]}"
    )
    return await OwnedRepository(db, Notebook, user.id).create(
        subject_id=subject.id,
        title="Bonds",
        slug=f"bonds-{uuid.uuid4().hex[:8]}",
        retrieval_settings={},
    )


# ---------------------------------------------------------------------------
# _check_quota
# ---------------------------------------------------------------------------


async def test_check_quota_allows_exactly_filling_it(
    db: AsyncSession, user: User
) -> None:
    await _check_quota(db, user.id, 1024 * 1024, quota_mb=1)  # exactly 1 MB, not over


async def test_check_quota_rejects_going_one_byte_over(
    db: AsyncSession, user: User
) -> None:
    with pytest.raises(QuotaExceeded):
        await _check_quota(db, user.id, 1024 * 1024 + 1, quota_mb=1)


# ---------------------------------------------------------------------------
# start_ingestion
# ---------------------------------------------------------------------------


async def make_source(
    db: AsyncSession, user: User, notebook: Notebook, *, status: SourceStatus
) -> Source:
    source = await OwnedRepository(db, Source, user.id).create(
        notebook_id=notebook.id,
        kind=SourceKind.MD,
        original_filename="notes.md",
        byte_size=0,
        status=status,
    )
    await db.flush()
    return source


async def test_start_ingestion_queues_from_pending(
    db: AsyncSession, user: User, notebook: Notebook, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = await make_source(db, user, notebook, status=SourceStatus.PENDING)
    sent: list[str] = []
    monkeypatch.setattr(
        "noema.workers.ingest.send", lambda source_id: sent.append(source_id)
    )

    out = await start_ingestion(source.id, user=user, db=db)

    assert out.status is SourceStatus.PENDING
    assert sent == [str(source.id)]


async def test_start_ingestion_clears_a_previous_error(
    db: AsyncSession, user: User, notebook: Notebook, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = await make_source(db, user, notebook, status=SourceStatus.FAILED)
    source.error = {"stage": "parse", "type": "ParseFailed", "detail": "boom"}
    await db.flush()
    monkeypatch.setattr("noema.workers.ingest.send", lambda source_id: None)

    out = await start_ingestion(source.id, user=user, db=db)

    assert out.error is None


async def test_start_ingestion_is_idempotent_while_already_running(
    db: AsyncSession, user: User, notebook: Notebook, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = await make_source(db, user, notebook, status=SourceStatus.EMBEDDING)
    sent: list[str] = []
    monkeypatch.setattr(
        "noema.workers.ingest.send", lambda source_id: sent.append(source_id)
    )

    out = await start_ingestion(source.id, user=user, db=db)

    assert out.status is SourceStatus.EMBEDDING
    assert sent == []


# ---------------------------------------------------------------------------
# list_sources / get_source / delete_source
# ---------------------------------------------------------------------------


async def test_list_sources_is_scoped_to_the_owner(
    db: AsyncSession, user: User, other_user: User, notebook: Notebook
) -> None:
    await make_source(db, user, notebook, status=SourceStatus.READY)
    other_notebook = await _another_notebook(db, other_user)
    await make_source(db, other_user, other_notebook, status=SourceStatus.READY)

    out = await list_sources(user=user, db=db, notebook_id=None)

    assert len(out) == 1


async def test_get_source_reports_its_chunk_count(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    source = await make_source(db, user, notebook, status=SourceStatus.READY)
    for i in range(3):
        db.add(
            Chunk(
                owner_id=user.id,
                source_id=source.id,
                notebook_id=notebook.id,
                ordinal=i,
                content=f"chunk {i}",
                token_count=2,
                heading_path=[],
            )
        )
    await db.flush()

    out = await get_source(source.id, user=user, db=db)

    assert out.chunk_count == 3


async def test_delete_source_removes_the_stored_file(
    db: AsyncSession, user: User, notebook: Notebook, settings: Settings, tmp_path: Path
) -> None:
    out = await upload_source(
        user=user, db=db, settings=settings, notebook_id=notebook.id, file=upload_file()
    )
    storage = LocalStorage(str(tmp_path))

    await delete_source(out.id, user=user, db=db, settings=settings)

    row = await db.get(Source, out.id)
    assert row is not None
    assert row.deleted_at is not None
    assert row.storage_key is not None
    with pytest.raises(StorageError):
        await storage.get(row.storage_key)


async def test_delete_source_with_no_stored_file_does_not_crash(
    db: AsyncSession, user: User, notebook: Notebook, settings: Settings
) -> None:
    source = await make_source(db, user, notebook, status=SourceStatus.PENDING)

    await delete_source(source.id, user=user, db=db, settings=settings)

    row = await db.get(Source, source.id)
    assert row is not None
    assert row.deleted_at is not None


# ---------------------------------------------------------------------------
# ingestion_events
# ---------------------------------------------------------------------------


async def test_ingestion_events_returns_immediately_for_a_terminal_source(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    source = await make_source(db, user, notebook, status=SourceStatus.READY)

    response = await ingestion_events(source.id, user=user, db=db)

    frames = [chunk async for chunk in response.body_iterator]
    assert len(frames) == 1
    assert b"event: status" in frames[0]


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


async def test_search_finds_content_from_an_ingested_source(
    db: AsyncSession, user: User, notebook: Notebook, settings: Settings, tmp_path: Path
) -> None:
    storage = LocalStorage(str(tmp_path))
    row = await OwnedRepository(db, Source, user.id).create(
        notebook_id=notebook.id,
        kind=SourceKind.MD,
        original_filename="cardiac.md",
        byte_size=len(MD),
        status=SourceStatus.PENDING,
    )
    key = f"{user.id}/{row.id}.md"
    await storage.put(key, MD)
    row.storage_key = key
    await db.flush()

    gateway = AIGateway(MockProvider(dimensions=settings.noema_embedding_dim))
    await ingest_source(db, row.id, storage=storage, gateway=gateway, settings=settings)

    hits = await search(
        user=user,
        db=db,
        gateway=AIGateway(MockProvider(dimensions=settings.noema_embedding_dim)),
        settings=settings,
        q="Diastole fills the ventricles",
        notebook_id=None,
        limit=20,
    )

    assert len(hits) > 0
    assert hits[0].source_id == row.id
