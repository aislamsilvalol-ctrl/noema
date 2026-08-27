"""Workspaces, subjects, notebooks and notes.

All access goes through :class:`OwnedRepository`, so tenancy scoping is structural
rather than per-endpoint discipline.
"""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select

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
from noema.core.errors import Conflict
from noema.db.models import Concept, Note, Notebook, Subject, Workspace
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
    """Create a workspace, refusing a slug collision cleanly.

    ``workspaces.slug`` is unique per owner at the DB level with no filtered/
    partial index, so an unchecked insert would surface a duplicate as a raw,
    unhandled ``IntegrityError`` (a 500, with no problem-details body) rather
    than the 409 every other conflict in this API returns. Checked first,
    same shape as ``AuthService.register``'s email check — a real, accepted
    TOCTOU window under true concurrency, same as that one.
    """
    slug = payload.slug or slugify(payload.title)
    if await db.scalar(
        select(Workspace.id).where(Workspace.owner_id == user.id, Workspace.slug == slug)
    ):
        raise Conflict(f'A workspace with the slug "{slug}" already exists.')

    workspace = await OwnedRepository(db, Workspace, user.id).create(
        title=payload.title, slug=slug
    )
    return WorkspaceOut.model_validate(workspace)


@router.delete("/workspaces/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> None:
    """Delete a workspace, refusing while anything still lives under it.

    ``Workspace`` has no ``deleted_at`` of its own, so ``OwnedRepository.delete``
    hard-deletes it — and the ``workspaces.id``/``subjects.id`` foreign keys are
    ``ondelete="CASCADE"`` (both at the DB and ORM relationship level), which would
    physically destroy every subject, notebook, note, card, and review underneath,
    bypassing the soft-delete/undo path each of those has on its own dedicated
    delete route. Refusing here keeps deletion of a workspace's contents on that
    same recoverable path instead of taking a silent shortcut around it.
    """
    await OwnedRepository(db, Workspace, user.id).get(workspace_id)  # 404s if not theirs

    if await db.scalar(
        select(Subject.id).where(
            Subject.workspace_id == workspace_id, Subject.owner_id == user.id
        )
    ):
        raise Conflict("Delete this workspace's subjects first.")
    if await db.scalar(
        select(Concept.id).where(
            Concept.workspace_id == workspace_id, Concept.owner_id == user.id
        )
    ):
        raise Conflict("Delete this workspace's concepts first.")

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
    """Create a subject, refusing a slug collision cleanly.

    Same reasoning as ``create_workspace``: ``subjects.slug`` is unique per
    workspace at the DB level, so this is checked first rather than left to
    surface as an unhandled ``IntegrityError``.
    """
    repo = OwnedRepository(db, Workspace, user.id)
    await repo.get(payload.workspace_id)  # 404s if it isn't theirs

    slug = payload.slug or slugify(payload.title)
    if await db.scalar(
        select(Subject.id).where(
            Subject.workspace_id == payload.workspace_id, Subject.slug == slug
        )
    ):
        raise Conflict(
            f'A subject with the slug "{slug}" already exists in this workspace.'
        )

    subject = await OwnedRepository(db, Subject, user.id).create(
        workspace_id=payload.workspace_id, title=payload.title, slug=slug
    )
    return SubjectOut.model_validate(subject)


@router.delete("/subjects/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subject(
    subject_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> None:
    """Delete a subject, refusing while any notebook row still exists under it.

    Same reasoning as ``delete_workspace``: ``Subject`` has no ``deleted_at``, so a
    hard delete here would cascade through every notebook (and everything under
    it) regardless of whether those notebooks were already soft-deleted — the
    cascade fires on the physical row, not on the flag. The check deliberately
    does not filter out already soft-deleted notebooks: their rows, and every
    card/review beneath them, are still real and still destroyable by the
    cascade. There is currently no route that purges a soft-deleted notebook, so
    a subject that has ever held one stays undeletable through this route —
    intentional, not a bug: nothing with real history disappears without an
    explicit purge decision, the same rule account deletion already follows.
    """
    await OwnedRepository(db, Subject, user.id).get(subject_id)  # 404s if not theirs

    if await db.scalar(
        select(Notebook.id).where(
            Notebook.subject_id == subject_id, Notebook.owner_id == user.id
        )
    ):
        raise Conflict("Delete this subject's notebooks first.")

    await OwnedRepository(db, Subject, user.id).delete(subject_id)


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
    """Create a notebook, refusing a slug collision cleanly.

    Same reasoning as ``create_workspace``. ``notebooks.slug`` is unique per
    subject with no filtered/partial index, so this check deliberately does
    not exclude an already soft-deleted notebook: its row, and the slug it
    holds, are still real at the DB level and would still collide.
    """
    await OwnedRepository(db, Subject, user.id).get(payload.subject_id)

    slug = payload.slug or slugify(payload.title)
    if await db.scalar(
        select(Notebook.id).where(
            Notebook.subject_id == payload.subject_id, Notebook.slug == slug
        )
    ):
        raise Conflict(
            f'A notebook with the slug "{slug}" already exists in this subject.'
        )

    notebook = await OwnedRepository(db, Notebook, user.id).create(
        subject_id=payload.subject_id,
        title=payload.title,
        slug=slug,
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
