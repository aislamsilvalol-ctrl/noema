"""update_card/approve_card/suspend_card/unsuspend_card/delete_card, against a
real database. None of these routes had any test coverage before (issue #88).

The main find here: ``Card.suspended_at`` was already load-bearing in every
due/candidate query (session planning, review recording, exports) but no route
ever set it -- a state every query correctly excluded and no card could ever
actually reach. ``suspend_card``/``unsuspend_card`` are the fix.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from noema.api.v1.study import (
    CardUpdate,
    approve_card,
    delete_card,
    list_cards,
    suspend_card,
    unsuspend_card,
    update_card,
)
from noema.core.config import Settings
from noema.core.errors import NotFound
from noema.db.models import Card, CardType, Notebook, Subject, User, Workspace
from noema.db.repository import OwnedRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def notebook(db: AsyncSession, user: User) -> Notebook:
    workspace = await OwnedRepository(db, Workspace, user.id).create(
        title="Bio", slug=f"bio-{uuid.uuid4().hex[:8]}"
    )
    subject = await OwnedRepository(db, Subject, user.id).create(
        workspace_id=workspace.id, title="Cells", slug=f"cells-{uuid.uuid4().hex[:8]}"
    )
    return await OwnedRepository(db, Notebook, user.id).create(
        subject_id=subject.id,
        title="Cell Biology",
        slug=f"cb-{uuid.uuid4().hex[:8]}",
        retrieval_settings={},
    )


@pytest.fixture
async def card(db: AsyncSession, user: User, notebook: Notebook) -> Card:
    return await OwnedRepository(db, Card, user.id).create(
        notebook_id=notebook.id,
        type=CardType.BASIC,
        front_md="Q",
        back_md="A",
        approved_at=None,
    )


async def test_update_card_changes_the_text(
    db: AsyncSession, user: User, card: Card
) -> None:
    out = await update_card(card.id, CardUpdate(front_md="New Q"), user=user, db=db)
    assert out.front_md == "New Q"
    assert out.back_md == "A"


async def test_approving_a_card_is_idempotent(
    db: AsyncSession, user: User, card: Card
) -> None:
    first = await approve_card(card.id, user=user, db=db)
    assert first.approved_at is not None

    second = await approve_card(card.id, user=user, db=db)
    assert second.approved_at == first.approved_at


async def test_suspending_a_card_is_idempotent_and_reversible(
    db: AsyncSession, user: User, card: Card
) -> None:
    assert card.suspended_at is None

    suspended = await suspend_card(card.id, user=user, db=db)
    assert suspended.suspended_at is not None

    suspended_again = await suspend_card(card.id, user=user, db=db)
    assert suspended_again.suspended_at == suspended.suspended_at

    unsuspended = await unsuspend_card(card.id, user=user, db=db)
    assert unsuspended.suspended_at is None


async def test_a_suspended_card_is_excluded_from_the_study_queue(
    db: AsyncSession, user: User, settings: Settings, notebook: Notebook, card: Card
) -> None:
    """The whole point of the column: prove a suspended card actually leaves
    the queue every gating query already claims to enforce against it."""
    await approve_card(card.id, user=user, db=db)

    before = await list_cards(
        user=user, db=db, settings=settings, notebook_id=notebook.id, limit=50
    )
    assert card.id in {c.id for c in before}

    await suspend_card(card.id, user=user, db=db)

    after = await list_cards(
        user=user, db=db, settings=settings, notebook_id=notebook.id, limit=50
    )
    assert card.id not in {c.id for c in after}


async def test_deleting_a_card_soft_deletes_it(
    db: AsyncSession, user: User, card: Card
) -> None:
    await delete_card(card.id, user=user, db=db)

    await db.refresh(card)
    assert card.deleted_at is not None


async def test_another_users_card_routes_all_404(
    db: AsyncSession, other_user: User, card: Card
) -> None:
    for coro in (
        update_card(card.id, CardUpdate(), user=other_user, db=db),
        approve_card(card.id, user=other_user, db=db),
        suspend_card(card.id, user=other_user, db=db),
        unsuspend_card(card.id, user=other_user, db=db),
        delete_card(card.id, user=other_user, db=db),
    ):
        with pytest.raises(NotFound):
            await coro
