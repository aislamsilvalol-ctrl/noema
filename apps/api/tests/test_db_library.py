"""Workspace/subject deletion must not silently cascade past soft-delete.

``Workspace`` and ``Subject`` have no ``deleted_at`` of their own, so
``OwnedRepository.delete`` hard-deletes them — and ``ondelete="CASCADE"`` on
``subjects.workspace_id``/``notebooks.subject_id`` (both at the DB and ORM
relationship level) would otherwise physically destroy every notebook, note,
card, and review underneath, bypassing the soft-delete/undo path each of those
has on its own dedicated route. These tests pin the refusal — including the
case that makes it non-optional: the notebook-existence check deliberately
does not exclude already soft-deleted notebooks, because their rows (and
every card/review beneath them) are still real and still destroyable by the
cascade. Soft-deleting every notebook first does not unblock a subject or
workspace delete; nothing currently purges a soft-deleted notebook, so a
subject/workspace that ever held one stays undeletable through this route.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.api.v1.library import (
    delete_notebook,
    delete_subject,
    delete_workspace,
    update_note,
    update_notebook,
)
from noema.api.v1.schemas import NotebookUpdate, NoteUpdate
from noema.core.errors import Conflict, NotFound
from noema.db.base import utcnow
from noema.db.models import (
    Card,
    CardSchedule,
    CardType,
    Concept,
    ConceptStatus,
    Note,
    Notebook,
    Review,
    Subject,
    User,
    Workspace,
)
from noema.db.repository import OwnedRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def workspace(db: AsyncSession, user: User) -> Workspace:
    return await OwnedRepository(db, Workspace, user.id).create(
        title="Bio", slug=f"bio-{uuid.uuid4().hex[:8]}"
    )


@pytest.fixture
async def subject(db: AsyncSession, user: User, workspace: Workspace) -> Subject:
    return await OwnedRepository(db, Subject, user.id).create(
        workspace_id=workspace.id, title="Cells", slug=f"cells-{uuid.uuid4().hex[:8]}"
    )


@pytest.fixture
async def notebook(db: AsyncSession, user: User, subject: Subject) -> Notebook:
    return await OwnedRepository(db, Notebook, user.id).create(
        subject_id=subject.id,
        title="Cell Biology",
        slug=f"cb-{uuid.uuid4().hex[:8]}",
        retrieval_settings={},
    )


async def test_an_empty_workspace_deletes_cleanly(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    await delete_workspace(workspace.id, user=user, db=db)

    assert await db.get(Workspace, workspace.id) is None


async def test_a_workspace_with_a_subject_refuses_to_delete(
    db: AsyncSession, user: User, workspace: Workspace, subject: Subject
) -> None:
    with pytest.raises(Conflict):
        await delete_workspace(workspace.id, user=user, db=db)

    assert await db.get(Workspace, workspace.id) is not None
    assert await db.get(Subject, subject.id) is not None


async def test_a_workspace_with_a_bare_concept_refuses_to_delete(
    db: AsyncSession, user: User, workspace: Workspace
) -> None:
    concept = Concept(
        owner_id=user.id,
        workspace_id=workspace.id,
        name="Osmosis",
        normalized_name="osmosis",
        status=ConceptStatus.CANDIDATE,
    )
    db.add(concept)
    await db.flush()

    with pytest.raises(Conflict):
        await delete_workspace(workspace.id, user=user, db=db)

    assert await db.get(Workspace, workspace.id) is not None


async def test_an_empty_subject_deletes_cleanly(
    db: AsyncSession, user: User, subject: Subject
) -> None:
    await delete_subject(subject.id, user=user, db=db)

    assert await db.get(Subject, subject.id) is None


async def test_a_subject_with_a_notebook_refuses_to_delete(
    db: AsyncSession, user: User, subject: Subject, notebook: Notebook
) -> None:
    with pytest.raises(Conflict):
        await delete_subject(subject.id, user=user, db=db)

    assert await db.get(Subject, subject.id) is not None
    assert await db.get(Notebook, notebook.id) is not None


async def test_soft_deleting_a_notebook_does_not_unblock_its_subject(
    db: AsyncSession,
    user: User,
    workspace: Workspace,
    subject: Subject,
    notebook: Notebook,
) -> None:
    """The regression this guard exists to prevent: soft-deleting every
    notebook first must NOT be a way to still reach the hard-delete cascade.

    ``Subject``/``Workspace`` have no purge path for a soft-deleted notebook,
    so once a subject has ever held one, it stays undeletable through this
    route — refusing forever is the safe failure mode, not a bug to route
    around. A card's schedule/review evidence, and the notebook/subject/
    workspace rows themselves, must all still be exactly where they were.
    """
    now = utcnow()
    card = await OwnedRepository(db, Card, user.id).create(
        notebook_id=notebook.id,
        type=CardType.BASIC,
        front_md="Q",
        back_md="A",
        approved_at=None,
    )
    schedule = await OwnedRepository(db, CardSchedule, user.id).create(
        card_id=card.id, due_at=now
    )
    review = Review(
        owner_id=user.id,
        card_id=card.id,
        rating=3,
        elapsed_ms=1000,
        state_after={},
        reviewed_at=now,
    )
    db.add(review)
    await db.flush()

    await delete_notebook(notebook.id, user=user, db=db)

    with pytest.raises(Conflict):
        await delete_subject(subject.id, user=user, db=db)
    with pytest.raises(Conflict):
        await delete_workspace(workspace.id, user=user, db=db)

    await db.refresh(card)
    assert card.deleted_at is None
    assert await db.get(CardSchedule, schedule.id) is not None
    assert (await db.scalar(select(Review).where(Review.id == review.id))) is not None
    assert await db.get(Notebook, notebook.id) is not None
    assert await db.get(Subject, subject.id) is not None
    assert await db.get(Workspace, workspace.id) is not None


async def test_deleting_another_users_workspace_is_refused(
    db: AsyncSession, other_user: User, workspace: Workspace
) -> None:
    with pytest.raises(NotFound):
        await delete_workspace(workspace.id, user=other_user, db=db)


async def test_deleting_another_users_subject_is_refused(
    db: AsyncSession, other_user: User, subject: Subject
) -> None:
    with pytest.raises(NotFound):
        await delete_subject(subject.id, user=other_user, db=db)


# ── PATCH clearing a nullable field ─────────────────────────────────────────────
#
# `OwnedRepository.update` used to skip any field whose value was `None`, even
# though its only two callers build `values` from `payload.model_dump(exclude_
# unset=True)` — a dict that already encodes "the client explicitly sent this
# field" versus "the client never mentioned it". Filtering out `None` on top of
# that collapsed the two cases FastAPI's own `exclude_unset` exists to tell
# apart: `PATCH {"description": null}` (clear it) became indistinguishable from
# not sending `description` at all (leave it alone) — a silent no-op instead of
# the clear the client asked for.


async def test_clearing_a_notebook_description_actually_clears_it(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    notebook.description = "Not empty"
    await db.flush()

    updated = await update_notebook(
        notebook.id, NotebookUpdate(description=None), user=user, db=db
    )

    assert updated.description is None


async def test_updating_a_notebook_title_leaves_description_untouched(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    notebook.description = "Keep me"
    await db.flush()

    updated = await update_notebook(
        notebook.id, NotebookUpdate(title="Renamed"), user=user, db=db
    )

    assert updated.title == "Renamed"
    assert updated.description == "Keep me"


async def test_clearing_a_notes_content_json_actually_clears_it(
    db: AsyncSession, user: User, notebook: Notebook
) -> None:
    note = await OwnedRepository(db, Note, user.id).create(
        notebook_id=notebook.id,
        title="Mitochondria",
        content_md="the powerhouse",
        content_json={"type": "doc"},
        links=[],
    )

    updated = await update_note(note.id, NoteUpdate(content_json=None), user=user, db=db)

    assert updated.content_json is None
    # content_md was never mentioned in this PATCH, so it must survive untouched.
    assert updated.content_md == "the powerhouse"
