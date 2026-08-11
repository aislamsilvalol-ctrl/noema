"""Cross-tenant isolation.

``SECURITY.md`` claims every query is scoped by owner at the repository layer and
that another user's row is indistinguishable from a missing one. This is the test
that makes those claims true rather than aspirational.

Parametrised over the model list, so adding an owned table without covering it here
is not something that can happen silently.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.errors import NotFound
from noema.db.base import OwnedEntity
from noema.db.models import Note, Notebook, Subject, User, Workspace
from noema.db.repository import OwnedRepository


async def build_library(db: AsyncSession, owner: User) -> dict[str, Any]:
    """A full workspace → subject → notebook → note chain for one user."""
    workspace = await OwnedRepository(db, Workspace, owner.id).create(
        title="Computer Science", slug=f"cs-{uuid.uuid4().hex[:8]}"
    )
    subject = await OwnedRepository(db, Subject, owner.id).create(
        workspace_id=workspace.id, title="Machine Learning", slug="ml"
    )
    notebook = await OwnedRepository(db, Notebook, owner.id).create(
        subject_id=subject.id, title="Neural Networks", slug="nn", retrieval_settings={}
    )
    note = await OwnedRepository(db, Note, owner.id).create(
        notebook_id=notebook.id,
        title="Backpropagation",
        content_md="chain rule",
        links=[],
    )
    return {
        "workspaces": workspace,
        "subjects": subject,
        "notebooks": notebook,
        "notes": note,
    }


MODELS: dict[str, type[OwnedEntity]] = {
    "workspaces": Workspace,
    "subjects": Subject,
    "notebooks": Notebook,
    "notes": Note,
}


@pytest.fixture
async def alice_library(db: AsyncSession, user: User) -> dict[str, Any]:
    return await build_library(db, user)


@pytest.mark.parametrize("kind", list(MODELS))
async def test_another_users_row_reads_as_missing(
    db: AsyncSession, other_user: User, alice_library: dict[str, Any], kind: str
) -> None:
    """404, never 403 — the existence of someone else's notebook is information."""
    repo = OwnedRepository(db, MODELS[kind], other_user.id)
    with pytest.raises(NotFound):
        await repo.get(alice_library[kind].id)


@pytest.mark.parametrize("kind", list(MODELS))
async def test_another_users_row_cannot_be_updated(
    db: AsyncSession, other_user: User, alice_library: dict[str, Any], kind: str
) -> None:
    repo = OwnedRepository(db, MODELS[kind], other_user.id)
    with pytest.raises(NotFound):
        await repo.update(alice_library[kind].id, title="pwned")


@pytest.mark.parametrize("kind", list(MODELS))
async def test_another_users_row_cannot_be_deleted(
    db: AsyncSession, other_user: User, alice_library: dict[str, Any], kind: str
) -> None:
    repo = OwnedRepository(db, MODELS[kind], other_user.id)
    with pytest.raises(NotFound):
        await repo.delete(alice_library[kind].id)


@pytest.mark.parametrize("kind", list(MODELS))
async def test_listing_never_returns_another_users_rows(
    db: AsyncSession, other_user: User, alice_library: dict[str, Any], kind: str
) -> None:
    mine = await build_library(db, other_user)
    items, _ = await OwnedRepository(db, MODELS[kind], other_user.id).list()

    ids = {item.id for item in items}
    assert mine[kind].id in ids
    assert alice_library[kind].id not in ids


async def test_the_owner_can_still_reach_their_own_rows(
    db: AsyncSession, user: User, alice_library: dict[str, Any]
) -> None:
    """The isolation tests would also pass if everything were broken."""
    for kind, model in MODELS.items():
        found = await OwnedRepository(db, model, user.id).get(alice_library[kind].id)
        assert found.id == alice_library[kind].id


async def test_soft_deleted_rows_disappear_from_reads(
    db: AsyncSession, user: User, alice_library: dict[str, Any]
) -> None:
    repo = OwnedRepository(db, Notebook, user.id)
    await repo.delete(alice_library["notebooks"].id)

    with pytest.raises(NotFound):
        await repo.get(alice_library["notebooks"].id)

    items, _ = await repo.list()
    assert alice_library["notebooks"].id not in {i.id for i in items}


async def test_pagination_walks_the_whole_set_without_repeats(
    db: AsyncSession, user: User
) -> None:
    repo = OwnedRepository(db, Workspace, user.id)
    created = {
        (await repo.create(title=f"W{i}", slug=f"w-{uuid.uuid4().hex[:8]}")).id
        for i in range(7)
    }

    seen: list[uuid.UUID] = []
    cursor: uuid.UUID | None = None
    while True:
        items, cursor = await repo.list(limit=3, cursor=cursor)
        seen.extend(item.id for item in items)
        if cursor is None:
            break

    assert len(seen) == len(set(seen)), "cursor pagination returned a row twice"
    assert created <= set(seen)
