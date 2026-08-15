"""Storing what an importer parsed.

Kept apart from the parsing on purpose. Reading someone else's file format is
where the surprises are and it is tested without a database; this half is
deliberately boring, and the only interesting decisions in it are about what
happens when an import is run twice.

Which it will be. People re-export a deck, add a hundred cards, and import the
same file again — so a card that is already here keeps its own review history,
rather than being added a second time or reset to whatever the file says. Missing
concept links may be repaired, but an import that damages the schedule of cards
you have been studying for months is worse than one that fails outright.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import (
    Card,
    CardOrigin,
    CardSchedule,
    CardState,
    CardType,
    Concept,
    ConceptStatus,
    Notebook,
    Subject,
)
from noema.importers import anki
from noema.knowledge.resolution import normalize_name

__all__ = ["ImportReport", "import_anki"]

#: A tag Anki decks carry through, so an import can be found and undone by hand.
IMPORTED_TAG = "imported/anki"

# Both Concept.name and Concept.normalized_name are varchar(200). Long Anki deck
# paths are rare but valid, so their full identity is retained in a digest rather
# than lost through a collision-prone slice.
CONCEPT_NAME_LIMIT = 200
CONCEPT_DIGEST_SEPARATOR = " "


@dataclass(frozen=True, slots=True)
class ImportReport:
    added: int
    #: Cards already here, not duplicated and with their history intact.
    unchanged: int
    scheduled: int
    skipped: dict[str, int]

    def summary(self) -> str:
        parts = [f"{self.added} cards added"]
        if self.scheduled:
            parts.append(f"{self.scheduled} keeping their review history")
        if self.unchanged:
            parts.append(f"{self.unchanged} already here with review history intact")
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

    workspace_id = await _lock_notebook_and_get_workspace(session, owner_id, notebook_id)
    existing = await _existing_cards(session, owner_id, notebook_id)
    concepts: dict[str, Concept] = {}

    added = 0
    unchanged = 0
    scheduled = 0

    for imported in result.cards:
        key = _key(imported.front, imported.back)
        if key in existing:
            unchanged += 1
            card = existing[key]
            if card.concept_id is None:
                concept = await _concept_for_deck(
                    session,
                    imported.deck,
                    owner_id=owner_id,
                    workspace_id=workspace_id,
                    cache=concepts,
                )
                card.concept_id = concept.id
            continue
        # Added to the mapping as we go, so a file containing the same card twice
        # does not produce two copies.
        concept = await _concept_for_deck(
            session,
            imported.deck,
            owner_id=owner_id,
            workspace_id=workspace_id,
            cache=concepts,
        )

        card = Card(
            owner_id=owner_id,
            notebook_id=notebook_id,
            concept_id=concept.id,
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
        existing[key] = card
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


async def _lock_notebook_and_get_workspace(
    session: AsyncSession, owner_id: uuid.UUID, notebook_id: uuid.UUID
) -> uuid.UUID:
    """Lock the notebook so concurrent imports see the preceding import's cards.

    The lock lasts for the caller's transaction. Parsing happens before this point,
    so imports only serialize while touching the database rather than while SQLite
    reads the uploaded package.
    """
    return (
        await session.execute(
            select(Subject.workspace_id)
            .select_from(Notebook)
            .join(Subject, Notebook.subject_id == Subject.id)
            .where(
                Notebook.id == notebook_id,
                Notebook.owner_id == owner_id,
                Notebook.deleted_at.is_(None),
            )
            .with_for_update(of=Notebook)
        )
    ).scalar_one()


async def _existing_cards(
    session: AsyncSession, owner_id: uuid.UUID, notebook_id: uuid.UUID
) -> dict[tuple[str, str], Card]:
    rows = await session.execute(
        select(Card)
        .where(
            Card.owner_id == owner_id,
            Card.notebook_id == notebook_id,
            Card.deleted_at.is_(None),
        )
        .order_by(Card.id)
    )
    existing: dict[tuple[str, str], Card] = {}
    for card in rows.scalars():
        existing.setdefault(_key(card.front_md, card.back_md), card)
    return existing


async def _concept_for_deck(
    session: AsyncSession,
    deck: str,
    *,
    owner_id: uuid.UUID,
    workspace_id: uuid.UUID,
    cache: dict[str, Concept],
) -> Concept:
    name, normalized_name = _concept_identity(deck)
    cached = cache.get(normalized_name)
    if cached is not None:
        return cached

    created_id = await session.scalar(
        insert(Concept)
        .values(
            owner_id=owner_id,
            workspace_id=workspace_id,
            name=name,
            normalized_name=normalized_name,
            aliases=[],
            source_chunk_ids=[],
            status=ConceptStatus.ACTIVE,
        )
        .on_conflict_do_nothing(
            index_elements=[Concept.workspace_id, Concept.normalized_name]
        )
        .returning(Concept.id)
    )
    if created_id is not None:
        concept = await session.get(Concept, created_id)
    else:
        concept = await session.scalar(
            select(Concept).where(
                Concept.owner_id == owner_id,
                Concept.workspace_id == workspace_id,
                Concept.normalized_name == normalized_name,
            )
        )

    if concept is None:
        raise RuntimeError("concept conflict did not resolve inside its workspace")

    concept = await _canonical_import_concept(
        session, concept, owner_id=owner_id, workspace_id=workspace_id
    )
    if concept.status is ConceptStatus.CANDIDATE:
        # A learner importing a deck is stronger evidence than a one-off extraction.
        concept.status = ConceptStatus.ACTIVE

    cache[normalized_name] = concept
    return concept


async def _canonical_import_concept(
    session: AsyncSession,
    concept: Concept,
    *,
    owner_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> Concept:
    """Follow valid merge chains without undoing curation.

    Rejected concepts remain rejected. A broken or cyclic merge chain likewise
    leaves its source untouched rather than producing the contradictory state of
    an active concept that still points at ``merged_into_id``.
    """
    seen: set[uuid.UUID] = set()
    current = concept
    while (
        current.status is ConceptStatus.MERGED
        and current.merged_into_id is not None
        and current.id not in seen
    ):
        seen.add(current.id)
        target = await session.scalar(
            select(Concept).where(
                Concept.id == current.merged_into_id,
                Concept.owner_id == owner_id,
                Concept.workspace_id == workspace_id,
            )
        )
        if target is None or target.id in seen:
            break
        current = target
    return current


def _concept_identity(deck: str) -> tuple[str, str]:
    """Display and unique key for a full Anki deck path.

    Normalisation follows the knowledge graph's existing rules over the entire
    path, so ``Medicine::Common`` and ``Biology::Common`` remain distinct while a
    concept created by another flow under the same rules is reused.
    """
    components = [" ".join(component.split()) for component in deck.split("::")]
    components = [component for component in components if component]
    canonical = "::".join(components) or "Imported"

    normalized = normalize_name(canonical) or (
        "deck" + CONCEPT_DIGEST_SEPARATOR + _digest(canonical)
    )

    if len(canonical) <= CONCEPT_NAME_LIMIT and len(normalized) <= CONCEPT_NAME_LIMIT:
        return canonical, normalized

    # For an overlong display value, store the bounded canonical identity in both
    # columns. That preserves cross-flow reuse because normalising Concept.name
    # produces exactly Concept.normalized_name, while the digest prevents prefix
    # truncation from conflating distinct deck paths.
    identity = _bounded_normalized(normalized)
    return identity, identity


def _bounded_normalized(value: str) -> str:
    if len(value) <= CONCEPT_NAME_LIMIT:
        return value
    suffix = CONCEPT_DIGEST_SEPARATOR + _digest(value)
    prefix = value[: CONCEPT_NAME_LIMIT - len(suffix)].rstrip()
    return prefix + suffix


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _key(front: str, back: str) -> tuple[str, str]:
    """What counts as the same card.

    Whitespace and case only, deliberately shallow: two cards differing by a
    word are two cards, and guessing harder would silently drop material the
    learner meant to keep.
    """
    return (" ".join(front.split()).casefold(), " ".join(back.split()).casefold())
