"""Storing what the Obsidian importer parsed, against a real database."""

from __future__ import annotations

import io
import uuid
import zipfile

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.base import utcnow
from noema.db.models import Note, Notebook, Subject, User, Workspace
from noema.db.repository import OwnedRepository
from noema.services.imports import import_obsidian

pytestmark = pytest.mark.asyncio


def zip_of(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


async def notebook_for(db: AsyncSession, owner: User) -> Notebook:
    workspace = await OwnedRepository(db, Workspace, owner.id).create(
        title="Vault", slug=f"vault-{uuid.uuid4().hex[:8]}"
    )
    subject = await OwnedRepository(db, Subject, owner.id).create(
        workspace_id=workspace.id, title="Notes", slug=f"notes-{uuid.uuid4().hex[:8]}"
    )
    return await OwnedRepository(db, Notebook, owner.id).create(
        subject_id=subject.id,
        title="Imported vault",
        slug=f"nb-{uuid.uuid4().hex[:8]}",
        retrieval_settings={},
    )


async def notes_in(db: AsyncSession, notebook: Notebook) -> list[Note]:
    rows = await db.execute(
        select(Note)
        .where(Note.notebook_id == notebook.id, Note.deleted_at.is_(None))
        .order_by(Note.title)
    )
    return list(rows.scalars())


async def test_notes_arrive_with_their_content_and_links(
    db: AsyncSession, user: User
) -> None:
    notebook = await notebook_for(db, user)

    report = await import_obsidian(
        db,
        zip_of({"Mitochondria.md": "See [[Cell]] for context."}),
        owner_id=user.id,
        notebook_id=notebook.id,
    )

    note = (await notes_in(db, notebook))[0]
    assert report.added == 1
    assert note.title == "Mitochondria"
    assert note.content_md == "See [[Cell]] for context."
    assert note.links == ["Cell"]


async def test_reimporting_updates_the_existing_note_by_title(
    db: AsyncSession, user: User
) -> None:
    notebook = await notebook_for(db, user)
    await import_obsidian(
        db,
        zip_of({"Note.md": "First version."}),
        owner_id=user.id,
        notebook_id=notebook.id,
    )
    first = (await notes_in(db, notebook))[0]

    report = await import_obsidian(
        db,
        zip_of({"Note.md": "Second version."}),
        owner_id=user.id,
        notebook_id=notebook.id,
    )

    notes = await notes_in(db, notebook)
    assert report.added == 0
    assert report.updated == 1
    assert len(notes) == 1
    assert notes[0].id == first.id
    assert notes[0].content_md == "Second version."


async def test_a_deleted_note_is_not_matched_and_a_fresh_one_is_added(
    db: AsyncSession, user: User
) -> None:
    notebook = await notebook_for(db, user)
    await import_obsidian(
        db, zip_of({"Note.md": "Original."}), owner_id=user.id, notebook_id=notebook.id
    )
    deleted = (await notes_in(db, notebook))[0]
    deleted.deleted_at = utcnow()
    await db.flush()

    report = await import_obsidian(
        db, zip_of({"Note.md": "New."}), owner_id=user.id, notebook_id=notebook.id
    )

    assert report.added == 1
    assert report.updated == 0
    notes = await notes_in(db, notebook)
    assert len(notes) == 1
    assert notes[0].id != deleted.id


async def test_the_same_title_in_another_notebook_is_untouched(
    db: AsyncSession, user: User
) -> None:
    first = await notebook_for(db, user)
    second = await notebook_for(db, user)
    await import_obsidian(
        db, zip_of({"Note.md": "In first."}), owner_id=user.id, notebook_id=first.id
    )

    await import_obsidian(
        db, zip_of({"Note.md": "In second."}), owner_id=user.id, notebook_id=second.id
    )

    assert (await notes_in(db, first))[0].content_md == "In first."
    assert (await notes_in(db, second))[0].content_md == "In second."
    assert await db.scalar(select(func.count()).select_from(Note)) == 2


async def test_import_cannot_cross_notebook_ownership(
    db: AsyncSession, user: User, other_user: User
) -> None:
    notebook = await notebook_for(db, user)

    with pytest.raises(NoResultFound):
        await import_obsidian(
            db,
            zip_of({"Note.md": "Text."}),
            owner_id=other_user.id,
            notebook_id=notebook.id,
        )

    assert await db.scalar(select(func.count()).select_from(Note)) == 0
