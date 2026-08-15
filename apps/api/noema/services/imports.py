"""Storing what an importer parsed.

Kept apart from the parsing on purpose. Reading someone else's file format is
where the surprises are and it is tested without a database; this half is
deliberately boring, and the only interesting decisions in it are about what
happens when an import is run twice.

Which it will be. People re-export a deck, add a hundred cards, and import the
same file again — so a card that is already here is left exactly as it is, with
its own review history, rather than added a second time or reset to whatever the
file says. An import that damages the schedule of cards you have been studying
for months is worse than one that fails outright.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import Card, CardOrigin, CardSchedule, CardState, CardType
from noema.importers import anki

__all__ = ["ImportReport", "import_anki"]

#: A tag Anki decks carry through, so an import can be found and undone by hand.
IMPORTED_TAG = "imported/anki"


@dataclass(frozen=True, slots=True)
class ImportReport:
    added: int
    #: Cards already in this notebook, left untouched with their history intact.
    unchanged: int
    scheduled: int
    skipped: dict[str, int]

    def summary(self) -> str:
        parts = [f"{self.added} cards added"]
        if self.scheduled:
            parts.append(f"{self.scheduled} keeping their review history")
        if self.unchanged:
            parts.append(f"{self.unchanged} already here and left alone")
        if self.skipped:
            dropped = ", ".join(
                f"{count} {reason}" for reason, count in self.skipped.items()
            )
            parts.append(f"skipped {dropped}")
        return ", ".join(parts) + "."


CARD_TYPES = {
    "basic": CardType.BASIC,
    "reverse": CardType.REVERSE,
    "cloze": CardType.CLOZE,
}


async def import_anki(
    session: AsyncSession,
    data: bytes,
    *,
    owner_id: uuid.UUID,
    notebook_id: uuid.UUID,
    now: datetime | None = None,
) -> ImportReport:
    """Parse an `.apkg` and add its cards to a notebook.

    Raises `anki.AnkiImportError` if the file cannot be read; nothing is written
    in that case, because parsing finishes before anything is added.
    """
    now = now or datetime.now(UTC)
    # zipfile and sqlite3 are both blocking, and a large deck is tens of
    # megabytes of SQLite. Parsing on the event loop would stall every other
    # request for the duration.
    result = await asyncio.to_thread(anki.read, data)

    existing = await _existing_fronts(session, owner_id, notebook_id)

    added = 0
    unchanged = 0
    scheduled = 0

    for imported in result.cards:
        key = _key(imported.front, imported.back)
        if key in existing:
            unchanged += 1
            continue
        # Added to the set as we go, so a file containing the same card twice
        # does not produce two copies.
        existing.add(key)

        card = Card(
            owner_id=owner_id,
            notebook_id=notebook_id,
            type=CARD_TYPES.get(imported.type, CardType.BASIC),
            front_md=imported.front,
            back_md=imported.back,
            # The learner's own cards, not AI drafts: nothing here needs approving
            # before it can be studied, and withholding them would be absurd —
            # they have been reviewing these for years.
            origin=CardOrigin.USER,
            approved_at=now,
        )
        session.add(card)
        # The schedule references the card's id, which only exists after a flush.
        await session.flush()
        added += 1

        session.add(_schedule(imported, card_id=card.id, owner_id=owner_id, now=now))
        if imported.schedule:
            scheduled += 1

    return ImportReport(
        added=added,
        unchanged=unchanged,
        scheduled=scheduled,
        skipped=dict(result.skipped),
    )


def _schedule(
    imported: anki.ImportedCard,
    *,
    card_id: uuid.UUID,
    owner_id: uuid.UUID,
    now: datetime,
) -> CardSchedule:
    if imported.schedule is None:
        # Never studied in Anki either, so it starts here as new — due now, and
        # the scheduler will take it from the first review.
        return CardSchedule(
            owner_id=owner_id,
            card_id=card_id,
            due_at=now,
            stability=0.0,
            difficulty=5.0,
            reps=0,
            lapses=0,
            state=CardState.NEW,
        )

    from_anki = imported.schedule
    return CardSchedule(
        owner_id=owner_id,
        card_id=card_id,
        due_at=from_anki.due_at,
        stability=from_anki.stability,
        difficulty=from_anki.difficulty,
        reps=from_anki.reps,
        lapses=from_anki.lapses,
        state=CardState.REVIEW,
        # Deliberately not set. `last_review_at` means "reviewed here", and the
        # elapsed time it feeds into FSRS is already carried by the due date. A
        # fabricated timestamp would be a review that never happened, in a log
        # whose whole value is that everything in it did.
        last_review_at=None,
    )


async def _existing_fronts(
    session: AsyncSession, owner_id: uuid.UUID, notebook_id: uuid.UUID
) -> set[tuple[str, str]]:
    rows = await session.execute(
        select(Card.front_md, Card.back_md).where(
            Card.owner_id == owner_id,
            Card.notebook_id == notebook_id,
            Card.deleted_at.is_(None),
        )
    )
    return {_key(front, back) for front, back in rows}


def _key(front: str, back: str) -> tuple[str, str]:
    """What counts as the same card.

    Whitespace and case only, deliberately shallow: two cards differing by a
    word are two cards, and guessing harder would silently drop material the
    learner meant to keep.
    """
    return (" ".join(front.split()).casefold(), " ".join(back.split()).casefold())
