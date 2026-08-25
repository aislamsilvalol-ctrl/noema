"""Bringing material in from other tools.

The response says what happened in numbers a learner can check against the deck
they exported — added, already here, skipped and why. An importer that answers
"done" is asking to be trusted about several thousand cards nobody is going to
count by hand.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile

# ruff: noqa: B008 — Form()/File() in defaults is FastAPI's documented signature style
from pydantic import BaseModel

from noema.api.v1 import deps
from noema.core.config import Settings
from noema.core.errors import NoemaError
from noema.db.models import Notebook
from noema.db.repository import OwnedRepository
from noema.importers.anki import AnkiImportError
from noema.importers.notion import NotionImportError
from noema.importers.obsidian import ObsidianImportError
from noema.importers.zotero import ZoteroImportError
from noema.services.imports import (
    import_anki,
    import_notion,
    import_obsidian,
    import_zotero,
)

router = APIRouter(
    prefix="/imports", tags=["imports"], dependencies=[Depends(deps.require_csrf)]
)


class UnreadableImport(NoemaError):
    """The file could not be read. The detail says what to do about it."""

    status_code = 422
    slug = "unreadable-import"
    title = "That file could not be imported"


class ImportOut(BaseModel):
    added: int
    #: Cards already in this notebook. Their review history and schedule are
    #: preserved; a missing concept link may be backfilled.
    unchanged: int
    #: How many arrived with their Anki intervals rather than as new cards.
    scheduled: int
    skipped: dict[str, int]
    summary: str


class NoteImportOut(BaseModel):
    added: int
    #: A note whose title matched one already here — updated in place. Notes
    #: carry no review history, so there is no "left alone" case to report.
    updated: int
    skipped: dict[str, int]
    summary: str


@router.post("/anki", response_model=ImportOut)
async def import_anki_package(
    user: deps.CurrentUser,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
    notebook_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
) -> ImportOut:
    """Import an Anki `.apkg` into a notebook, keeping its review history."""
    await OwnedRepository(db, Notebook, user.id).get(notebook_id)
    data = await _read_upload(file, settings)

    try:
        report = await import_anki(db, data, owner_id=user.id, notebook_id=notebook_id)
    except AnkiImportError as error:
        # The parser's messages are written for the learner and each says what to
        # do next, so they are passed through rather than replaced with a generic
        # failure.
        raise UnreadableImport(str(error)) from error

    return ImportOut(
        added=report.added,
        unchanged=report.unchanged,
        scheduled=report.scheduled,
        skipped=report.skipped,
        summary=report.summary(),
    )


@router.post("/obsidian", response_model=NoteImportOut)
async def import_obsidian_vault(
    user: deps.CurrentUser,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
    notebook_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
) -> NoteImportOut:
    """Import a zipped Obsidian vault's notes into a notebook."""
    await OwnedRepository(db, Notebook, user.id).get(notebook_id)
    data = await _read_upload(file, settings)

    try:
        report = await import_obsidian(
            db, data, owner_id=user.id, notebook_id=notebook_id
        )
    except ObsidianImportError as error:
        raise UnreadableImport(str(error)) from error

    return NoteImportOut(
        added=report.added,
        updated=report.updated,
        skipped=report.skipped,
        summary=report.summary(),
    )


@router.post("/notion", response_model=NoteImportOut)
async def import_notion_export(
    user: deps.CurrentUser,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
    notebook_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
) -> NoteImportOut:
    """Import a zipped Notion export's pages into a notebook as notes."""
    await OwnedRepository(db, Notebook, user.id).get(notebook_id)
    data = await _read_upload(file, settings)

    try:
        report = await import_notion(db, data, owner_id=user.id, notebook_id=notebook_id)
    except NotionImportError as error:
        raise UnreadableImport(str(error)) from error

    return NoteImportOut(
        added=report.added,
        updated=report.updated,
        skipped=report.skipped,
        summary=report.summary(),
    )


@router.post("/zotero", response_model=NoteImportOut)
async def import_zotero_library(
    user: deps.CurrentUser,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
    notebook_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
) -> NoteImportOut:
    """Import a Zotero CSL-JSON export's references into a notebook as notes."""
    await OwnedRepository(db, Notebook, user.id).get(notebook_id)
    data = await _read_upload(file, settings)

    try:
        report = await import_zotero(db, data, owner_id=user.id, notebook_id=notebook_id)
    except ZoteroImportError as error:
        raise UnreadableImport(str(error)) from error

    return NoteImportOut(
        added=report.added,
        updated=report.updated,
        skipped=report.skipped,
        summary=report.summary(),
    )


async def _read_upload(file: UploadFile, settings: Settings) -> bytes:
    data = await file.read()
    limit = settings.noema_max_upload_mb * 1024 * 1024
    if len(data) > limit:
        raise UnreadableImport(
            "That file is larger than this deployment's "
            f"{settings.noema_max_upload_mb}MB limit."
        )
    return data
