"""Source upload and ingestion.

Upload is a direct multipart POST rather than a presigned URL: with the local
storage driver there is nothing to presign, and validation has to see the bytes
before they are stored anyway.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

# ruff: noqa: B008 — Form()/File() in defaults is FastAPI's documented signature style
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from noema.api.v1 import deps
from noema.core.errors import Conflict, NotFound, QuotaExceeded
from noema.db.models import Chunk, Notebook, Source, SourceKind, SourceStatus
from noema.db.repository import OwnedRepository
from noema.ingestion import parsers
from noema.ingestion.storage import build_storage, storage_key
from noema.ingestion.validation import check_upload

router = APIRouter(
    prefix="/sources", tags=["sources"], dependencies=[Depends(deps.require_csrf)]
)

#: How often the progress stream polls. Ingestion stages take seconds to minutes, so
#: anything faster is just load.
POLL_SECONDS = 1.0
STREAM_TIMEOUT_SECONDS = 15 * 60


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    notebook_id: uuid.UUID
    kind: SourceKind
    original_filename: str | None
    byte_size: int
    page_count: int | None
    status: SourceStatus
    error: dict[str, Any] | None
    created_at: datetime


class SourceDetail(SourceOut):
    chunk_count: int
    metadata: dict[str, Any]


@router.post("", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
async def upload_source(
    user: deps.CurrentUser,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
    notebook_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
) -> SourceOut:
    """Validate, store and queue a file for ingestion."""
    await OwnedRepository(db, Notebook, user.id).get(notebook_id)

    data = await file.read()
    check = check_upload(data, file.filename, max_upload_mb=settings.noema_max_upload_mb)

    if not parsers.available(check.kind):
        raise parsers.ParserUnavailable(
            f"This deployment cannot read {check.kind.value.upper()} files. "
            f"Install the {parsers.OPTIONAL[check.kind]} extra and restart."
        )

    await _check_quota(db, user.id, check.byte_size, settings.noema_user_storage_quota_mb)

    # Re-uploading the same file reuses the existing source instead of paying for a
    # second parse and a second set of embeddings.
    duplicate = await db.scalar(
        select(Source).where(
            Source.owner_id == user.id,
            Source.checksum_sha256 == check.checksum_sha256,
            Source.deleted_at.is_(None),
        )
    )
    if duplicate is not None:
        where = (
            "this notebook"
            if duplicate.notebook_id == notebook_id
            else "another notebook"
        )
        raise Conflict(
            f"This file is already in {where} as "
            f"{duplicate.original_filename or 'an existing source'}.",
            source_id=str(duplicate.id),
        )

    source = await OwnedRepository(db, Source, user.id).create(
        notebook_id=notebook_id,
        kind=check.kind,
        original_filename=file.filename,
        checksum_sha256=check.checksum_sha256,
        byte_size=check.byte_size,
        status=SourceStatus.PENDING,
        source_metadata={},
    )

    key = storage_key(user.id, source.id, check.kind.value)
    await build_storage(settings).put(key, data)
    source.storage_key = key
    await db.flush()

    return SourceOut.model_validate(source)


@router.post("/{source_id}/ingest", response_model=SourceOut)
async def start_ingestion(
    source_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> SourceOut:
    """Queue the pipeline. Idempotent while a run is already in flight."""
    source = await OwnedRepository(db, Source, user.id).get(source_id)

    if source.status not in {
        SourceStatus.PENDING,
        SourceStatus.FAILED,
        SourceStatus.READY,
    }:
        return SourceOut.model_validate(source)

    source.status = SourceStatus.PENDING
    source.error = None
    await db.flush()

    from noema.workers import ingest

    ingest.send(str(source.id))
    return SourceOut.model_validate(source)


@router.get("", response_model=list[SourceOut])
async def list_sources(
    user: deps.CurrentUser, db: deps.SessionDep, notebook_id: uuid.UUID | None = None
) -> list[SourceOut]:
    items, _ = await OwnedRepository(db, Source, user.id).list(
        limit=100, notebook_id=notebook_id
    )
    return [SourceOut.model_validate(item) for item in items]


@router.get("/{source_id}", response_model=SourceDetail)
async def get_source(
    source_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> SourceDetail:
    source = await OwnedRepository(db, Source, user.id).get(source_id)
    chunk_count = await db.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.source_id == source.id)
    )
    return SourceDetail(
        **SourceOut.model_validate(source).model_dump(),
        chunk_count=int(chunk_count or 0),
        metadata=source.source_metadata,
    )


@router.get("/{source_id}/events")
async def ingestion_events(
    source_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> StreamingResponse:
    """Per-stage ingestion progress.

    Polling the row rather than subscribing to the broker: the status is already
    durable, and a client that reconnects gets the current state instead of having
    missed the events it was away for.
    """
    await OwnedRepository(db, Source, user.id).get(source_id)

    async def events() -> AsyncIterator[bytes]:
        last: str | None = None
        waited = 0.0

        while waited < STREAM_TIMEOUT_SECONDS:
            source = await OwnedRepository(db, Source, user.id).get(source_id)
            await db.refresh(source)

            if source.status.value != last:
                last = source.status.value
                yield _sse(
                    "status",
                    {
                        "status": source.status.value,
                        "page_count": source.page_count,
                        "error": source.error,
                    },
                )

            if source.status in {SourceStatus.READY, SourceStatus.FAILED}:
                return

            await asyncio.sleep(POLL_SECONDS)
            waited += POLL_SECONDS

        yield _sse("error", {"message": "Ingestion is taking unusually long."})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
    )


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: uuid.UUID,
    user: deps.CurrentUser,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
) -> None:
    """Soft-delete the row and hard-delete the file.

    Chunks and embeddings cascade. The stored file goes immediately — keeping a
    user's PDF around after they deleted it is not a feature.
    """
    repo = OwnedRepository(db, Source, user.id)
    source = await repo.get(source_id)

    if source.storage_key:
        await build_storage(settings).delete(source.storage_key)

    await repo.delete(source_id)


async def _check_quota(
    db: deps.SessionDep, owner_id: uuid.UUID, incoming: int, quota_mb: int
) -> None:
    used = await db.scalar(
        select(func.coalesce(func.sum(Source.byte_size), 0)).where(
            Source.owner_id == owner_id, Source.deleted_at.is_(None)
        )
    )
    if int(used or 0) + incoming > quota_mb * 1024 * 1024:
        raise QuotaExceeded(
            f"This would exceed your {quota_mb} MB storage quota. "
            "Delete a source to make room."
        )


def _sse(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode()


__all__ = ["NotFound", "router"]
