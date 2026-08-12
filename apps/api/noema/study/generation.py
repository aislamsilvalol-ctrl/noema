"""Generating flashcards from a notebook's material.

Generated cards arrive unapproved and stay out of the rotation until a human has
read them. That is not friction for its own sake: a card the learner never agreed
to is a claim they will memorise anyway, and spaced repetition is very good at
making a wrong card permanent.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.logging import get_logger
from noema.db.models import Card, CardOrigin, CardType, Chunk, Concept, ConceptStatus
from noema.knowledge.resolution import normalize_name
from noema.prompts import PROMPT_DIR, load
from noema.providers.base import (
    Message,
    ProviderError,
    Role,
    StructuredRequest,
    TaskClass,
)
from noema.providers.gateway import AIGateway

log = get_logger(__name__)

__all__ = ["GeneratedCard", "generate_cards", "parse_cards"]

BATCH_SIZE = 4
MAX_FRONT = 500
MAX_BACK = 2_000
MAX_CARDS_PER_BATCH = 12

#: Read once at import. The schema is a static file shipped with the code, and
#: reading it per request would be blocking IO inside the event loop.
SCHEMA: dict[str, Any] = json.loads(
    (PROMPT_DIR / "generate.cards.schema.json").read_text(encoding="utf-8")
)

ALLOWED_TYPES = {
    "basic": CardType.BASIC,
    "definition": CardType.DEFINITION,
    "concept": CardType.CONCEPT,
    "code": CardType.CODE,
}


@dataclass(frozen=True, slots=True)
class GeneratedCard:
    front: str
    back: str
    type: CardType
    concept_name: str
    source_chunk_ids: list[str]


async def generate_cards(
    session: AsyncSession,
    notebook_id: uuid.UUID,
    *,
    owner_id: uuid.UUID,
    gateway: AIGateway,
    limit: int = 20,
    model: str | None = None,
) -> list[Card]:
    """Generate cards for a notebook and store them unapproved."""
    chunks = (
        await session.execute(
            select(Chunk.id, Chunk.content)
            .where(Chunk.notebook_id == notebook_id, Chunk.owner_id == owner_id)
            .order_by(Chunk.ordinal)
            .limit(60)
        )
    ).all()

    if not chunks:
        return []

    prompt = load("generate.cards")
    generated: list[GeneratedCard] = []

    for start in range(0, len(chunks), BATCH_SIZE):
        if len(generated) >= limit:
            break

        batch = chunks[start : start + BATCH_SIZE]
        passages = "\n\n".join(
            f"<passage>\n{content.strip()}\n</passage>" for _, content in batch
        )

        try:
            payload = await gateway.structured(
                StructuredRequest(
                    messages=[
                        Message(role=Role.SYSTEM, content=prompt.body),
                        Message(
                            role=Role.USER,
                            content=f"<PASSAGES>\n{passages}\n</PASSAGES>",
                        ),
                    ],
                    json_schema=SCHEMA,
                    task=TaskClass.GENERATE_CARDS,
                    model=model,
                )
            )
        except ProviderError as exc:
            log.warning("cards.batch_failed", offset=start, error=str(exc))
            continue

        generated.extend(parse_cards(payload, [str(cid) for cid, _ in batch]))

    return await _store(session, generated[:limit], notebook_id, owner_id)


def parse_cards(
    payload: dict[str, Any], source_chunk_ids: Sequence[str]
) -> list[GeneratedCard]:
    """Validate a model response into cards worth showing a human."""
    raw = payload.get("cards")
    if not isinstance(raw, list):
        return []

    cards: list[GeneratedCard] = []
    for item in raw[:MAX_CARDS_PER_BATCH]:
        if not isinstance(item, dict):
            continue

        front = str(item.get("front") or "").strip()[:MAX_FRONT]
        back = str(item.get("back") or "").strip()[:MAX_BACK]
        if not front or not back:
            continue

        # A card whose answer restates the question tests nothing, and it is the
        # most common way generated decks pad themselves out.
        if normalize_name(front) == normalize_name(back):
            continue

        cards.append(
            GeneratedCard(
                front=front,
                back=back,
                type=ALLOWED_TYPES.get(str(item.get("type")), CardType.BASIC),
                concept_name=str(item.get("concept") or "").strip()[:200],
                source_chunk_ids=list(source_chunk_ids),
            )
        )

    return cards


async def _store(
    session: AsyncSession,
    generated: Sequence[GeneratedCard],
    notebook_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> list[Card]:
    if not generated:
        return []

    workspace_concepts = {
        concept.normalized_name: concept
        for concept in (
            await session.scalars(
                select(Concept).where(
                    Concept.owner_id == owner_id,
                    Concept.status != ConceptStatus.MERGED,
                )
            )
        ).all()
    }

    existing_fronts = {
        front.strip().lower()
        for front in (
            await session.scalars(
                select(Card.front_md).where(
                    Card.notebook_id == notebook_id, Card.deleted_at.is_(None)
                )
            )
        ).all()
    }

    stored: list[Card] = []
    for candidate in generated:
        if candidate.front.lower() in existing_fronts:
            continue
        existing_fronts.add(candidate.front.lower())

        concept = workspace_concepts.get(normalize_name(candidate.concept_name))
        card = Card(
            owner_id=owner_id,
            notebook_id=notebook_id,
            concept_id=concept.id if concept else None,
            type=candidate.type,
            front_md=candidate.front,
            back_md=candidate.back,
            source_chunk_ids=[uuid.UUID(cid) for cid in candidate.source_chunk_ids],
            origin=CardOrigin.AI,
            # approved_at stays null: nothing generated enters the rotation until a
            # human has read it.
            approved_at=None,
        )
        session.add(card)
        stored.append(card)

    await session.flush()
    log.info("cards.generated", notebook_id=str(notebook_id), count=len(stored))
    return stored
