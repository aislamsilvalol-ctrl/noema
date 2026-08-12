"""Export and deletion.

The README promises you can take your data out and take it away. These tests are
what make that a feature rather than a sentence: an export that opens without NOEMA,
a deletion that locks the account immediately, and a purge that removes the files as
well as the rows.
"""

from __future__ import annotations

import json
import uuid
import zipfile
from datetime import timedelta
from io import BytesIO

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.config import Settings
from noema.core.errors import Unauthorized
from noema.db.base import utcnow
from noema.db.models import (
    Note,
    Notebook,
    Session,
    Source,
    SourceKind,
    Subject,
    User,
    Workspace,
)
from noema.db.repository import OwnedRepository
from noema.ingestion.storage import LocalStorage, Storage, StorageError, storage_key
from noema.services.account import (
    GRACE_DAYS,
    build_export,
    purge_expired_accounts,
    request_deletion,
)
from noema.services.auth import AuthService

pytestmark = pytest.mark.asyncio


async def seed(db: AsyncSession, owner: User, storage: Storage) -> Source:
    """A library with one note and one uploaded file."""
    workspace = await OwnedRepository(db, Workspace, owner.id).create(
        title="Computer Science", slug=f"cs-{uuid.uuid4().hex[:8]}"
    )
    subject = await OwnedRepository(db, Subject, owner.id).create(
        workspace_id=workspace.id, title="Machine Learning", slug="ml"
    )
    notebook = await OwnedRepository(db, Notebook, owner.id).create(
        subject_id=subject.id, title="Neural Networks", slug="nn", retrieval_settings={}
    )
    await OwnedRepository(db, Note, owner.id).create(
        notebook_id=notebook.id,
        title="Backprop / notes",
        content_md="the chain rule, applied backwards",
        links=[],
    )
    source = await OwnedRepository(db, Source, owner.id).create(
        notebook_id=notebook.id,
        kind=SourceKind.PDF,
        original_filename="lecture 3.pdf",
        byte_size=5,
    )
    source.storage_key = storage_key(owner.id, source.id, "pdf")
    await storage.put(source.storage_key, b"%PDF-")
    await db.flush()
    return source


async def test_export_opens_without_noema(
    db: AsyncSession, user: User, tmp_path: object
) -> None:
    """Notes are Markdown and uploads are byte-identical.

    This is the whole point of the archive: a zip only NOEMA can read is lock-in
    with extra steps.
    """
    storage = LocalStorage(str(tmp_path))
    await seed(db, user, storage)

    archive = zipfile.ZipFile(BytesIO(await build_export(db, user, storage=storage)))
    names = set(archive.namelist())

    assert {"README.md", "account.json", "library.json", "study.json"} <= names

    notes = [n for n in names if n.startswith("notes/")]
    assert notes == ["notes/Neural Networks/Backprop  notes.md"], (
        "notes go in a folder named after their notebook, with a filename that "
        "cannot escape it"
    )
    assert "the chain rule" in archive.read(notes[0]).decode()

    sources = [n for n in names if n.startswith("sources/")]
    assert archive.read(sources[0]) == b"%PDF-", "uploads come back unchanged"

    account = json.loads(archive.read("account.json"))
    assert account["email"] == user.email


async def test_export_is_scoped_to_the_owner(
    db: AsyncSession, user: User, other_user: User, tmp_path: object
) -> None:
    """An export is not a way to read someone else's library."""
    storage = LocalStorage(str(tmp_path))
    await seed(db, user, storage)
    await seed(db, other_user, storage)

    archive = zipfile.ZipFile(BytesIO(await build_export(db, user, storage=storage)))
    library = json.loads(archive.read("library.json"))

    assert len(library["workspaces"]) == 1
    assert len(library["sources"]) == 1


async def test_deletion_locks_the_account_immediately(
    db: AsyncSession, settings: Settings
) -> None:
    """Signed out now; purged later.

    A grace period exists so a decision made at 2am can be undone — not so the
    account keeps working for a month.
    """
    auth = AuthService(db, settings)
    user = await auth.register("leaving@example.com", "correct-horse-battery", "Leo")
    await auth.issue_session(user, user_agent="pytest", ip="127.0.0.1")

    request = await request_deletion(db, user)

    assert request.purge_after - request.requested_at == timedelta(days=GRACE_DAYS)
    live = (
        await db.scalars(
            select(Session).where(
                Session.user_id == user.id, Session.revoked_at.is_(None)
            )
        )
    ).all()
    assert live == [], "existing sessions end at once, not in thirty days"

    with pytest.raises(Unauthorized):
        await auth.authenticate("leaving@example.com", "correct-horse-battery")


async def test_purge_respects_the_grace_period(
    db: AsyncSession, user: User, tmp_path: object
) -> None:
    """A freshly deleted account is still recoverable."""
    storage = LocalStorage(str(tmp_path))
    await seed(db, user, storage)
    await request_deletion(db, user)

    assert await purge_expired_accounts(db, storage=storage) == []
    assert await db.get(User, user.id) is not None


async def test_purge_removes_rows_and_files(
    db: AsyncSession, user: User, other_user: User, tmp_path: object
) -> None:
    """Deleted has to mean deleted, on disk as well as in the database.

    Rows cascade from ``users``; stored files do not, so the purge deletes them
    explicitly. An untouched second account proves the purge is not a truncate.
    """
    storage = LocalStorage(str(tmp_path))
    source = await seed(db, user, storage)
    survivor = await seed(db, other_user, storage)
    assert source.storage_key is not None and survivor.storage_key is not None

    await request_deletion(db, user)
    user.deleted_at = utcnow() - timedelta(days=GRACE_DAYS + 1)
    await db.flush()

    purged = await purge_expired_accounts(db, storage=storage)

    assert purged == [user.id]
    assert await db.get(User, user.id) is None
    assert (
        await db.scalars(select(Source.id).where(Source.owner_id == user.id))
    ).all() == []

    with pytest.raises(StorageError):
        await storage.get(source.storage_key)

    assert await db.get(User, other_user.id) is not None
    assert await storage.get(survivor.storage_key) == b"%PDF-"


class BrokenStorage(LocalStorage):
    """Storage whose deletes always fail.

    ``LocalStorage.delete`` is ``missing_ok``, so deleting an absent file would not
    exercise the tolerance at all — the test would pass without the ``except``
    clause existing. This makes the failure real.
    """

    async def delete(self, key: str) -> None:
        raise StorageError("The object store said no.")


async def test_purge_survives_a_failing_delete(
    db: AsyncSession, user: User, tmp_path: object
) -> None:
    """One unreadable key must not keep an account alive forever."""
    storage = BrokenStorage(str(tmp_path))
    await seed(db, user, storage)

    await request_deletion(db, user)
    user.deleted_at = utcnow() - timedelta(days=GRACE_DAYS + 1)
    await db.flush()

    assert await purge_expired_accounts(db, storage=storage) == [user.id]
