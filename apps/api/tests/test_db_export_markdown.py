"""Turning a notebook's own notes into a zip of Markdown, against a real database."""

from __future__ import annotations

import uuid
import zipfile
from io import BytesIO

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.errors import NotFound
from noema.db.base import utcnow
from noema.db.models import Note, Notebook, Subject, User, Workspace
from noema.db.repository import OwnedRepository
from noema.services.exports import export_markdown

pytestmark = pytest.mark.asyncio


async def notebook_for(db: AsyncSession, owner: User) -> Notebook:
    workspace = await OwnedRepository(db, Workspace, owner.id).create(
        title="Languages", slug=f"lang-{uuid.uuid4().hex[:8]}"
    )
    subject = await OwnedRepository(db, Subject, owner.id).create(
        workspace_id=workspace.id, title="Japanese", slug=f"jp-{uuid.uuid4().hex[:8]}"
    )
    return await OwnedRepository(db, Notebook, owner.id).create(
        subject_id=subject.id,
        title="Core 2k",
        slug=f"core-{uuid.uuid4().hex[:8]}",
        retrieval_settings={},
    )


async def add_note(
    db: AsyncSession,
    notebook: Notebook,
    owner: User,
    *,
    title: str = "Untitled",
    content: str = "",
    deleted: bool = False,
) -> Note:
    note = Note(
        owner_id=owner.id,
        notebook_id=notebook.id,
        title=title,
        content_md=content,
        deleted_at=utcnow() if deleted else None,
    )
    db.add(note)
    await db.flush()
    return note


def _names(data: bytes) -> set[str]:
    with zipfile.ZipFile(BytesIO(data)) as archive:
        return set(archive.namelist())


def _read(data: bytes, name: str) -> str:
    with zipfile.ZipFile(BytesIO(data)) as archive:
        return archive.read(name).decode()


async def test_a_note_leaves_as_markdown(db: AsyncSession, user: User) -> None:
    notebook = await notebook_for(db, user)
    await add_note(db, notebook, user, title="Kanji radicals", content="Water is 水.")

    data = await export_markdown(db, owner_id=user.id, notebook_id=notebook.id)

    assert _names(data) == {"Kanji radicals.md"}
    assert _read(data, "Kanji radicals.md") == "# Kanji radicals\n\nWater is 水."


async def test_notes_from_another_notebook_are_not_included(
    db: AsyncSession, user: User
) -> None:
    included = await notebook_for(db, user)
    other = await notebook_for(db, user)
    await add_note(db, included, user, title="Included")
    await add_note(db, other, user, title="Not included")

    data = await export_markdown(db, owner_id=user.id, notebook_id=included.id)

    assert _names(data) == {"Included.md"}


async def test_a_deleted_note_is_not_exported(db: AsyncSession, user: User) -> None:
    notebook = await notebook_for(db, user)
    await add_note(db, notebook, user, title="Gone", deleted=True)

    data = await export_markdown(db, owner_id=user.id, notebook_id=notebook.id)

    assert _names(data) == set()


async def test_two_notes_sharing_a_title_do_not_collide(
    db: AsyncSession, user: User
) -> None:
    notebook = await notebook_for(db, user)
    await add_note(db, notebook, user, title="Untitled", content="first")
    await add_note(db, notebook, user, title="Untitled", content="second")

    data = await export_markdown(db, owner_id=user.id, notebook_id=notebook.id)

    assert _names(data) == {"Untitled.md", "Untitled (2).md"}


async def test_an_empty_notebook_still_produces_a_readable_zip(
    db: AsyncSession, user: User
) -> None:
    notebook = await notebook_for(db, user)

    data = await export_markdown(db, owner_id=user.id, notebook_id=notebook.id)

    assert _names(data) == set()


async def test_export_cannot_cross_notebook_ownership(
    db: AsyncSession, user: User, other_user: User
) -> None:
    notebook = await notebook_for(db, user)
    await add_note(db, notebook, user)

    with pytest.raises(NotFound):
        await export_markdown(db, owner_id=other_user.id, notebook_id=notebook.id)
