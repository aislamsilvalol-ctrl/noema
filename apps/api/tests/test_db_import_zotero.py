"""Storing what the Zotero importer parsed, against a real database.

Re-import idempotency, deleted-note isolation, cross-notebook isolation and the
ownership check are `import_obsidian`, `import_notion` and `import_zotero` sharing
the exact same `_import_notes` — see `tests/test_db_import_obsidian.py` for that
matrix. What is worth proving again here is that this reader's own shape —
byline-only content, no links — actually reaches a real row.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import Note, Notebook, Subject, User, Workspace
from noema.db.repository import OwnedRepository
from noema.services.imports import import_zotero


def csl(*items: dict[str, object]) -> bytes:
    return json.dumps(list(items)).encode()


async def notebook_for(db: AsyncSession, owner: User) -> Notebook:
    workspace = await OwnedRepository(db, Workspace, owner.id).create(
        title="Workspace", slug=f"ws-{uuid.uuid4().hex[:8]}"
    )
    subject = await OwnedRepository(db, Subject, owner.id).create(
        workspace_id=workspace.id, title="Notes", slug=f"notes-{uuid.uuid4().hex[:8]}"
    )
    return await OwnedRepository(db, Notebook, owner.id).create(
        subject_id=subject.id,
        title="Imported library",
        slug=f"nb-{uuid.uuid4().hex[:8]}",
        retrieval_settings={},
    )


async def test_a_reference_arrives_as_a_titled_note_with_no_links(
    db: AsyncSession, user: User
) -> None:
    notebook = await notebook_for(db, user)

    report = await import_zotero(
        db,
        csl(
            {
                "id": "smith2020",
                "type": "article-journal",
                "title": "The Chain Rule Revisited",
                "author": [{"family": "Smith", "given": "Jane"}],
                "issued": {"date-parts": [[2020]]},
            }
        ),
        owner_id=user.id,
        notebook_id=notebook.id,
    )

    note = await db.scalar(select(Note).where(Note.notebook_id == notebook.id))
    assert report.added == 1
    assert note is not None
    assert note.title == "The Chain Rule Revisited"
    assert "Jane Smith (2020)" in note.content_md
    assert note.links == []


async def test_a_reference_with_no_title_is_skipped_not_written(
    db: AsyncSession, user: User
) -> None:
    notebook = await notebook_for(db, user)

    report = await import_zotero(
        db,
        csl({"id": "x", "type": "webpage"}),
        owner_id=user.id,
        notebook_id=notebook.id,
    )

    count = await db.scalar(select(Note).where(Note.notebook_id == notebook.id))
    assert report.added == 0
    assert report.skipped["no title"] == 1
    assert count is None


async def test_import_cannot_cross_notebook_ownership(
    db: AsyncSession, user: User, other_user: User
) -> None:
    notebook = await notebook_for(db, user)

    with pytest.raises(NoResultFound):
        await import_zotero(
            db,
            csl({"id": "x", "type": "webpage", "title": "Note"}),
            owner_id=other_user.id,
            notebook_id=notebook.id,
        )
