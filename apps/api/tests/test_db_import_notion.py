"""Storing what the Notion importer parsed, against a real database.

Re-import idempotency, deleted-note isolation, cross-notebook isolation and the
ownership check are `import_obsidian` and `import_notion` sharing the exact same
`_import_notes` — see `tests/test_db_import_obsidian.py` for that matrix. What is
worth proving again here is that this reader's own format quirks — the id
suffix, the redundant heading, page-link resolution — actually reach a real row.
"""

from __future__ import annotations

import io
import uuid
import zipfile

import pytest
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import Note, Notebook, Subject, User, Workspace
from noema.db.repository import OwnedRepository
from noema.services.imports import import_notion

pytestmark = pytest.mark.asyncio

HASH_A = "1a2b3c4d5e6f78901a2b3c4d5e6f7890"
HASH_B = "aabbccddeeff00112233445566778899"


def zip_of(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


async def notebook_for(db: AsyncSession, owner: User) -> Notebook:
    workspace = await OwnedRepository(db, Workspace, owner.id).create(
        title="Workspace", slug=f"ws-{uuid.uuid4().hex[:8]}"
    )
    subject = await OwnedRepository(db, Subject, owner.id).create(
        workspace_id=workspace.id, title="Notes", slug=f"notes-{uuid.uuid4().hex[:8]}"
    )
    return await OwnedRepository(db, Notebook, owner.id).create(
        subject_id=subject.id,
        title="Imported workspace",
        slug=f"nb-{uuid.uuid4().hex[:8]}",
        retrieval_settings={},
    )


async def test_a_page_arrives_with_its_id_suffix_stripped_and_its_links(
    db: AsyncSession, user: User
) -> None:
    notebook = await notebook_for(db, user)
    body = f"# Mitochondria\n\nSee [Cell](Cell%20{HASH_B}.md)."

    report = await import_notion(
        db,
        zip_of({f"Mitochondria {HASH_A}.md": body}),
        owner_id=user.id,
        notebook_id=notebook.id,
    )

    note = await db.scalar(select(Note).where(Note.notebook_id == notebook.id))
    assert report.added == 1
    assert note is not None
    assert note.title == "Mitochondria"
    assert note.content_md == f"See [Cell](Cell%20{HASH_B}.md)."
    assert note.links == ["Cell"]


async def test_import_cannot_cross_notebook_ownership(
    db: AsyncSession, user: User, other_user: User
) -> None:
    notebook = await notebook_for(db, user)

    with pytest.raises(NoResultFound):
        await import_notion(
            db,
            zip_of({f"Note {HASH_A}.md": "Text."}),
            owner_id=other_user.id,
            notebook_id=notebook.id,
        )
