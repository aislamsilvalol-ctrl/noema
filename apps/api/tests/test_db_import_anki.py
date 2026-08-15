"""Storing an imported Anki deck.

The parser has its own tests; these cover the half that touches the database,
and mostly they cover one scenario: importing the same deck twice. People
re-export a deck after adding a hundred cards and import it again, and the
failure that matters is not a duplicate — it is a card someone has been studying
for two years having its schedule reset to whatever the file said.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from anki_deck import CREATED, build
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
from noema.services.imports import import_anki

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


async def cards_in(db: AsyncSession, notebook: Notebook) -> list[Card]:
    rows = await db.execute(
        select(Card).where(Card.notebook_id == notebook.id).order_by(Card.front_md)
    )
    return list(rows.scalars())


async def test_cards_arrive_studyable(
    db: AsyncSession, user: User, tmp_path: Path
) -> None:
    """Imported cards are the learner's own, so nothing waits for approval.

    AI drafts are inert until approved. These are cards someone has been
    reviewing for years — withholding them would be absurd.
    """
    notebook = await notebook_for(db, user)

    report = await import_anki(
        db,
        build(tmp_path, [{"flds": "ねこ\x1fcat"}]),
        owner_id=user.id,
        notebook_id=notebook.id,
    )

    assert report.added == 1
    card = (await cards_in(db, notebook))[0]
    assert card.front_md == "ねこ"
    assert card.origin is CardOrigin.USER
    assert card.approved_at is not None
    assert card.type is CardType.BASIC


async def test_the_anki_interval_becomes_the_schedule(
    db: AsyncSession, user: User, tmp_path: Path
) -> None:
    notebook = await notebook_for(db, user)

    await import_anki(
        db,
        build(
            tmp_path, [{"flds": "q\x1fa", "type": 2, "ivl": 90, "due": 300, "reps": 8}]
        ),
        owner_id=user.id,
        notebook_id=notebook.id,
    )

    card = (await cards_in(db, notebook))[0]
    schedule = await db.scalar(
        select(CardSchedule).where(CardSchedule.card_id == card.id)
    )
    assert schedule is not None
    assert schedule.state is CardState.REVIEW
    assert schedule.stability == 90.0
    assert schedule.reps == 8
    assert schedule.due_at.date() == CREATED.date() + timedelta(days=300)
    # Never reviewed *here*, and the review log's value is that everything in it
    # actually happened.
    assert schedule.last_review_at is None


async def test_an_unstudied_card_starts_new(
    db: AsyncSession, user: User, tmp_path: Path
) -> None:
    notebook = await notebook_for(db, user)

    await import_anki(
        db,
        build(tmp_path, [{"flds": "q\x1fa", "type": 0}]),
        owner_id=user.id,
        notebook_id=notebook.id,
    )

    card = (await cards_in(db, notebook))[0]
    schedule = await db.scalar(
        select(CardSchedule).where(CardSchedule.card_id == card.id)
    )
    assert schedule is not None
    assert schedule.state is CardState.NEW
    assert schedule.reps == 0


# ── Importing the same deck twice ────────────────────────────────────────────


async def test_reimporting_does_not_duplicate(
    db: AsyncSession, user: User, tmp_path: Path
) -> None:
    notebook = await notebook_for(db, user)
    deck = build(tmp_path, [{"flds": "q\x1fa"}, {"flds": "b\x1f2"}])

    first = await import_anki(db, deck, owner_id=user.id, notebook_id=notebook.id)
    second = await import_anki(db, deck, owner_id=user.id, notebook_id=notebook.id)

    assert first.added == 2
    assert second.added == 0
    assert second.unchanged == 2
    assert (
        await db.scalar(
            select(func.count()).select_from(Card).where(Card.notebook_id == notebook.id)
        )
        == 2
    )


async def test_reimporting_leaves_an_existing_schedule_alone(
    db: AsyncSession, user: User, tmp_path: Path
) -> None:
    """The card has been studied here since the first import.

    A second import must not drag it back to where the file says it was — that
    is real progress destroyed by a routine action, and it would be discovered
    weeks later as "the scheduling feels wrong".
    """
    notebook = await notebook_for(db, user)
    deck = build(tmp_path, [{"flds": "q\x1fa", "type": 2, "ivl": 10}])

    await import_anki(db, deck, owner_id=user.id, notebook_id=notebook.id)
    card = (await cards_in(db, notebook))[0]
    schedule = await db.scalar(
        select(CardSchedule).where(CardSchedule.card_id == card.id)
    )
    assert schedule is not None

    # Studied here: stability grows well past what the file claims.
    schedule.stability = 400.0
    schedule.reps = 25
    await db.flush()

    await import_anki(db, deck, owner_id=user.id, notebook_id=notebook.id)

    await db.refresh(schedule)
    assert schedule.stability == 400.0
    assert schedule.reps == 25


async def test_a_deck_containing_the_same_card_twice_adds_it_once(
    db: AsyncSession, user: User, tmp_path: Path
) -> None:
    notebook = await notebook_for(db, user)

    report = await import_anki(
        db,
        build(tmp_path, [{"flds": "q\x1fa"}, {"flds": " Q \x1f A "}]),
        owner_id=user.id,
        notebook_id=notebook.id,
    )

    assert report.added == 1


async def test_the_same_deck_in_another_notebook_is_a_separate_import(
    db: AsyncSession, user: User, tmp_path: Path
) -> None:
    """Notebooks are how someone separates material; sharing cards across them
    silently would merge two things they deliberately kept apart."""
    first = await notebook_for(db, user)
    second = await notebook_for(db, user)
    deck = build(tmp_path, [{"flds": "q\x1fa"}])

    await import_anki(db, deck, owner_id=user.id, notebook_id=first.id)
    report = await import_anki(db, deck, owner_id=user.id, notebook_id=second.id)

    assert report.added == 1


async def test_the_report_is_checkable_against_the_deck(
    db: AsyncSession, user: User, tmp_path: Path
) -> None:
    notebook = await notebook_for(db, user)

    report = await import_anki(
        db,
        build(
            tmp_path,
            [
                {"flds": "a\x1f1", "type": 2, "ivl": 30},
                {"flds": "b\x1f2"},
                {"flds": 'c\x1f<img src="x.png">'},
            ],
        ),
        owner_id=user.id,
        notebook_id=notebook.id,
    )

    assert report.added == 2
    assert report.scheduled == 1
    assert sum(report.skipped.values()) == 1
    assert "2 cards added" in report.summary()
