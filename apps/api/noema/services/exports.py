"""Building an export from one notebook, in whichever format was asked for.

The mirror of `noema.services.imports`: turns rows this deployment owns into the
dataclasses the writer in `noema.exporters` needs. Anki gets the cards — a deck
this owner can open, and decides what a card must have to be worth sending:
approved, not suspended, not deleted. A card nobody has ever agreed to study, or
has since turned off, has no business in someone's Anki deck. Markdown gets the
notes, which is `noema.services.account.build_export`'s job for a whole account
already; this is the same idea narrowed to one notebook, for someone who wants
just that much of their material and not a full account archive.
"""

from __future__ import annotations

import io
import re
import uuid
import zipfile
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.base import utcnow
from noema.db.models import Card, CardSchedule, CardState, CardType, Note, Notebook
from noema.db.repository import OwnedRepository
from noema.exporters import anki
from noema.exporters.anki import ExportCard, ExportSchedule

__all__ = ["ExportReport", "export_anki", "export_markdown"]

#: Same rule `noema.services.account` uses for a filename that cannot escape its
#: folder or break an unzipper — kept local rather than imported so this module
#: does not reach into that one's private helpers for one regex.
_UNSAFE_PATH = re.compile(r"[^\w\- ]+")

#: `CardSchedule.state` values Anki already times in whole days. The rest —
#: `new` and `learning` — leave unscheduled; see `noema.exporters.anki`.
DAY_TIMED = {CardState.REVIEW, CardState.RELEARNING}


@dataclass(frozen=True, slots=True)
class ExportReport:
    data: bytes
    exported: int
    scheduled: int
    skipped: dict[str, int]

    def summary(self) -> str:
        text = f"{self.exported} cards, {self.scheduled} with their review history"
        if self.skipped:
            dropped = ", ".join(
                f"{count} {reason}" for reason, count in self.skipped.items()
            )
            text += f". Left behind: {dropped}"
        return f"{text}."


async def export_anki(
    session: AsyncSession, *, owner_id: uuid.UUID, notebook_id: uuid.UUID
) -> ExportReport:
    """Every studyable card in `notebook_id`, as a `.apkg` this owner can open."""
    notebook = await OwnedRepository(session, Notebook, owner_id).get(notebook_id)

    rows = await session.execute(
        select(Card, CardSchedule)
        .outerjoin(CardSchedule, CardSchedule.card_id == Card.id)
        .where(
            Card.owner_id == owner_id,
            Card.notebook_id == notebook_id,
            Card.deleted_at.is_(None),
            Card.suspended_at.is_(None),
            Card.approved_at.is_not(None),
        )
        .order_by(Card.id)
    )

    cards: list[ExportCard] = []
    skipped: Counter[str] = Counter()
    for card, schedule in rows.all():
        if card.type is CardType.IMAGE:
            skipped["hold an image, which isn't carried across"] += 1
            continue
        cards.append(_export_card(card, schedule))

    created = utcnow()
    data = anki.write(cards, deck_name=notebook.title, created=created)

    # `anki.write` has its own reasons to leave a card behind (an unsafe cloze
    # reconstruction) that this loop cannot see coming — the reply describes
    # what actually left, not what was offered.
    scheduled = sum(1 for card in cards if card.schedule is not None)
    return ExportReport(
        data=data, exported=len(cards), scheduled=scheduled, skipped=skipped
    )


async def export_markdown(
    session: AsyncSession, *, owner_id: uuid.UUID, notebook_id: uuid.UUID
) -> bytes:
    """Every note in `notebook_id`, as a zip of Markdown files this owner can open.

    Flashcards have their own destination — `export_anki` — since Anki is the
    format that keeps their review history meaningful. This carries the prose.
    """
    await OwnedRepository(session, Notebook, owner_id).get(notebook_id)

    notes = (
        await session.scalars(
            select(Note)
            .where(
                Note.owner_id == owner_id,
                Note.notebook_id == notebook_id,
                Note.deleted_at.is_(None),
            )
            .order_by(Note.title)
        )
    ).all()

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        used: set[str] = set()
        for note in notes:
            path = f"{_safe_filename(note.title)}.md"
            suffix = 1
            while path in used:
                suffix += 1
                path = f"{_safe_filename(note.title)} ({suffix}).md"
            used.add(path)
            archive.writestr(path, f"# {note.title}\n\n{note.content_md}")

    return buffer.getvalue()


def _safe_filename(name: str) -> str:
    cleaned = _UNSAFE_PATH.sub("", name).strip() or "untitled"
    return cleaned[:80]


def _export_card(card: Card, schedule: CardSchedule | None) -> ExportCard:
    export_schedule = None
    if schedule is not None and schedule.state in DAY_TIMED:
        export_schedule = ExportSchedule(
            stability=schedule.stability,
            difficulty=schedule.difficulty,
            reps=schedule.reps,
            lapses=schedule.lapses,
            due_at=schedule.due_at,
        )

    return ExportCard(
        front=card.front_md,
        back=card.back_md,
        type=card.type.value,
        tags=(),
        schedule=export_schedule,
    )
