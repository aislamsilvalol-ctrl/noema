"""Workspaces, subjects, notebooks and notes.

All access goes through :class:`OwnedRepository`, so tenancy scoping is structural
rather than per-endpoint discipline.
"""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, Query, status

from noema.api.v1 import deps
from noema.api.v1.schemas import (
    NotebookCreate,
    NotebookOut,
    NotebookUpdate,
    NoteCreate,
    NoteOut,
    NoteUpdate,
    Page,
    SubjectCreate,
    SubjectOut,
    WorkspaceCreate,
    WorkspaceOut,
)
from noema.db.models import Note, Notebook, Subject, Workspace
from noema.db.repository import OwnedRepository

router = APIRouter(tags=["library"], dependencies=[Depends(deps.require_csrf)])

WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:200] or "untitled"


# ── Workspaces ────────────────────────────────────────────────────────────────


@router.get("/workspaces", response_model=Page[WorkspaceOut])
async def list_workspaces(
    user: deps.CurrentUser, db: deps.SessionDep, cursor: uuid.UUID | None = None
) -> Page[WorkspaceOut]:
    items, next_cursor = await OwnedRepository(db, Workspace, user.id).list(cursor=cursor)
    return Page(
        items=[WorkspaceOut.model_validate(i) for i in items], next_cursor=next_cursor
    )


@router.post(
    "/workspaces", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED
)
async def create_workspace(
    payload: WorkspaceCreate, user: deps.CurrentUser, db: deps.SessionDep
) -> WorkspaceOut:
    workspace = await OwnedRepository(db, Workspace, user.id).create(
        title=payload.title, slug=payload.slug or slugify(payload.title)
    )
    return WorkspaceOut.model_validate(workspace)


@router.delete("/workspaces/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> None:
    await OwnedRepository(db, Workspace, user.id).delete(workspace_id)


# ── Subjects ──────────────────────────────────────────────────────────────────


@router.get("/subjects", response_model=Page[SubjectOut])
async def list_subjects(
    user: deps.CurrentUser,
    db: deps.SessionDep,
    workspace_id: uuid.UUID | None = None,
    cursor: uuid.UUID | None = None,
) -> Page[SubjectOut]:
    items, next_cursor = await OwnedRepository(db, Subject, user.id).list(
        cursor=cursor, workspace_id=workspace_id
    )
    return Page(
        items=[SubjectOut.model_validate(i) for i in items], next_cursor=next_cursor
    )


@router.post("/subjects", response_model=SubjectOut, status_code=status.HTTP_201_CREATED)
async def create_subject(
    payload: SubjectCreate, user: deps.CurrentUser, db: deps.SessionDep
) -> SubjectOut:
    repo = OwnedRepository(db, Workspace, user.id)
    await repo.get(payload.workspace_id)  # 404s if it isn't theirs

    subject = await OwnedRepository(db, Subject, user.id).create(
        workspace_id=payload.workspace_id,
        title=payload.title,
        slug=payload.slug or slugify(payload.title),
    )
    return SubjectOut.model_validate(subject)


# ── Notebooks ─────────────────────────────────────────────────────────────────


@router.get("/notebooks", response_model=Page[NotebookOut])
async def list_notebooks(
    user: deps.CurrentUser,
    db: deps.SessionDep,
    subject_id: uuid.UUID | None = None,
    cursor: uuid.UUID | None = None,
    limit: int = Query(default=50, le=100),
) -> Page[NotebookOut]:
    items, next_cursor = await OwnedRepository(db, Notebook, user.id).list(
        cursor=cursor, limit=limit, subject_id=subject_id
    )
    return Page(
        items=[NotebookOut.model_validate(i) for i in items], next_cursor=next_cursor
    )


@router.post(
    "/notebooks", response_model=NotebookOut, status_code=status.HTTP_201_CREATED
)
async def create_notebook(
    payload: NotebookCreate, user: deps.CurrentUser, db: deps.SessionDep
) -> NotebookOut:
    await OwnedRepository(db, Subject, user.id).get(payload.subject_id)

    notebook = await OwnedRepository(db, Notebook, user.id).create(
        subject_id=payload.subject_id,
        title=payload.title,
        slug=payload.slug or slugify(payload.title),
        description=payload.description,
        retrieval_settings={},
    )
    return NotebookOut.model_validate(notebook)


@router.get("/notebooks/{notebook_id}", response_model=NotebookOut)
async def get_notebook(
    notebook_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> NotebookOut:
    notebook = await OwnedRepository(db, Notebook, user.id).get(notebook_id)
    return NotebookOut.model_validate(notebook)


@router.patch("/notebooks/{notebook_id}", response_model=NotebookOut)
async def update_notebook(
    notebook_id: uuid.UUID,
    payload: NotebookUpdate,
    user: deps.CurrentUser,
    db: deps.SessionDep,
) -> NotebookOut:
    notebook = await OwnedRepository(db, Notebook, user.id).update(
        notebook_id, **payload.model_dump(exclude_unset=True)
    )
    return NotebookOut.model_validate(notebook)


@router.delete("/notebooks/{notebook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notebook(
    notebook_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> None:
    await OwnedRepository(db, Notebook, user.id).delete(notebook_id)


# ── Notes ─────────────────────────────────────────────────────────────────────


@router.get("/notes", response_model=Page[NoteOut])
async def list_notes(
    user: deps.CurrentUser,
    db: deps.SessionDep,
    notebook_id: uuid.UUID | None = None,
    cursor: uuid.UUID | None = None,
) -> Page[NoteOut]:
    items, next_cursor = await OwnedRepository(db, Note, user.id).list(
        cursor=cursor, notebook_id=notebook_id
    )
    return Page(items=[NoteOut.model_validate(i) for i in items], next_cursor=next_cursor)


@router.post("/notes", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def create_note(
    payload: NoteCreate, user: deps.CurrentUser, db: deps.SessionDep
) -> NoteOut:
    await OwnedRepository(db, Notebook, user.id).get(payload.notebook_id)

    note = await OwnedRepository(db, Note, user.id).create(
        notebook_id=payload.notebook_id,
        title=payload.title,
        content_md=payload.content_md,
        content_json=payload.content_json,
        links=WIKILINK.findall(payload.content_md),
    )
    return NoteOut.model_validate(note)


@router.get("/notes/{note_id}", response_model=NoteOut)
async def get_note(
    note_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> NoteOut:
    return NoteOut.model_validate(await OwnedRepository(db, Note, user.id).get(note_id))


@router.patch("/notes/{note_id}", response_model=NoteOut)
async def update_note(
    note_id: uuid.UUID, payload: NoteUpdate, user: deps.CurrentUser, db: deps.SessionDep
) -> NoteOut:
    values = payload.model_dump(exclude_unset=True)
    if payload.content_md is not None:
        values["links"] = WIKILINK.findall(payload.content_md)

    note = await OwnedRepository(db, Note, user.id).update(note_id, **values)
    return NoteOut.model_validate(note)


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> None:
    await OwnedRepository(db, Note, user.id).delete(note_id)
