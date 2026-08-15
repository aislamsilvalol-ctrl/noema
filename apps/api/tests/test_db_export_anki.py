"""Turning a notebook's own cards into a `.apkg`, against a real database."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.errors import NotFound
from noema.db.base import utcnow
from noema.db.models import (
    Card,
    CardOrigin,
    CardSchedule,
    CardState,
    CardType,
    Notebook,
    Subject,
    User,
    Workspace,
)
from noema.db.repository import OwnedRepository
from noema.importers.anki import read
from noema.services.exports import export_anki

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


async def add_card(
    db: AsyncSession,
    notebook: Notebook,
    owner: User,
    *,
    front: str = "Front",
    back: str = "Back",
    card_type: CardType = CardType.BASIC,
    approved: bool = True,
    suspended: bool = False,
    deleted: bool = False,
    schedule: bool = False,
    state: CardState = CardState.REVIEW,
) -> Card:
    now = utcnow()
    card = Card(
        owner_id=owner.id,
        notebook_id=notebook.id,
        type=card_type,
        front_md=front,
        back_md=back,
        origin=CardOrigin.USER,
        approved_at=now if approved else None,
        suspended_at=now if suspended else None,
        deleted_at=now if deleted else None,
    )
    db.add(card)
    await db.flush()

    if schedule:
        db.add(
            CardSchedule(
                owner_id=owner.id,
                card_id=card.id,
                due_at=now + timedelta(days=10),
                last_review_at=now,
                stability=10.0,
                difficulty=4.0,
                reps=5,
                lapses=1,
                state=state,
            )
        )
        await db.flush()

    return card


async def test_studyable_cards_leave_with_the_notebooks_name_as_the_deck(
    db: AsyncSession, user: User
) -> None:
    notebook = await notebook_for(db, user)
    await add_card(
        db, notebook, user, front="What is a mitochondrion?", back="An organelle"
    )

    report = await export_anki(db, owner_id=user.id, notebook_id=notebook.id)

    result = read(report.data)
    assert report.exported == 1
    assert len(result.cards) == 1
    assert result.cards[0].front == "What is a mitochondrion?"
    assert result.cards[0].deck == "Core 2k"


async def test_a_reviewed_cards_history_leaves_with_it(
    db: AsyncSession, user: User
) -> None:
    notebook = await notebook_for(db, user)
    await add_card(db, notebook, user, schedule=True, state=CardState.REVIEW)

    report = await export_anki(db, owner_id=user.id, notebook_id=notebook.id)

    result = read(report.data)
    assert report.scheduled == 1
    assert result.cards[0].schedule is not None
    assert result.cards[0].schedule.reps == 5


async def test_a_relearning_cards_history_leaves_with_it(
    db: AsyncSession, user: User
) -> None:
    notebook = await notebook_for(db, user)
    await add_card(db, notebook, user, schedule=True, state=CardState.RELEARNING)

    report = await export_anki(db, owner_id=user.id, notebook_id=notebook.id)

    result = read(report.data)
    assert result.cards[0].schedule is not None


async def test_a_new_cards_schedule_does_not_leave(db: AsyncSession, user: User) -> None:
    notebook = await notebook_for(db, user)
    await add_card(db, notebook, user, schedule=True, state=CardState.NEW)

    report = await export_anki(db, owner_id=user.id, notebook_id=notebook.id)

    result = read(report.data)
    assert report.scheduled == 0
    assert result.cards[0].schedule is None


async def test_a_card_with_no_schedule_row_still_exports(
    db: AsyncSession, user: User
) -> None:
    notebook = await notebook_for(db, user)
    await add_card(db, notebook, user, schedule=False)

    report = await export_anki(db, owner_id=user.id, notebook_id=notebook.id)

    assert report.exported == 1
    assert report.scheduled == 0


async def test_an_unapproved_card_is_not_exported(db: AsyncSession, user: User) -> None:
    notebook = await notebook_for(db, user)
    await add_card(db, notebook, user, approved=False)

    report = await export_anki(db, owner_id=user.id, notebook_id=notebook.id)

    assert report.exported == 0


async def test_a_suspended_card_is_not_exported(db: AsyncSession, user: User) -> None:
    notebook = await notebook_for(db, user)
    await add_card(db, notebook, user, suspended=True)

    report = await export_anki(db, owner_id=user.id, notebook_id=notebook.id)

    assert report.exported == 0


async def test_a_deleted_card_is_not_exported(db: AsyncSession, user: User) -> None:
    notebook = await notebook_for(db, user)
    await add_card(db, notebook, user, deleted=True)

    report = await export_anki(db, owner_id=user.id, notebook_id=notebook.id)

    assert report.exported == 0


async def test_an_image_card_is_counted_as_skipped_not_exported(
    db: AsyncSession, user: User
) -> None:
    notebook = await notebook_for(db, user)
    await add_card(db, notebook, user, card_type=CardType.IMAGE)

    report = await export_anki(db, owner_id=user.id, notebook_id=notebook.id)

    assert report.exported == 0
    assert sum(report.skipped.values()) == 1


async def test_cards_from_another_notebook_are_not_included(
    db: AsyncSession, user: User
) -> None:
    included = await notebook_for(db, user)
    other = await notebook_for(db, user)
    await add_card(db, included, user, front="Included")
    await add_card(db, other, user, front="Not included")

    report = await export_anki(db, owner_id=user.id, notebook_id=included.id)

    result = read(report.data)
    assert [card.front for card in result.cards] == ["Included"]


async def test_export_cannot_cross_notebook_ownership(
    db: AsyncSession, user: User, other_user: User
) -> None:
    notebook = await notebook_for(db, user)
    await add_card(db, notebook, user)

    with pytest.raises(NotFound):
        await export_anki(db, owner_id=other_user.id, notebook_id=notebook.id)
