"""FlashcardEngine: cards written by the lesson, not by a button.

When a concept has just been shown understood (or the lesson moves past it),
and no card exists for it yet, two to four atomic cards are generated on the
economy tier and stored on the journey — unapproved, exactly like every other
AI card: they enter the learner's rotation the first time the learner turns
one over in the lesson (`recall`), which is the reading the approval rule
asks for. The recall also writes the FSRS review and a mastery event, so the
deck in the chat and the deck at `/review` are one deck.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.errors import NotFound
from noema.core.logging import get_logger
from noema.db.base import utcnow
from noema.db.models import (
    Card,
    CardOrigin,
    CardType,
    LearningJourney,
    StudentConceptState,
)
from noema.engines import fsrs
from noema.prompts import load
from noema.providers.base import (
    Message,
    ProviderError,
    Role,
    StructuredRequest,
    TaskClass,
)
from noema.providers.gateway import AIGateway
from noema.study.review import record_review

from .student import StudentModel

log = get_logger(__name__)

__all__ = ["CARDS_SCHEMA", "generate_for_concept", "parse_cards", "recall", "should_card"]

CARDS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "front": {"type": "string"},
                    "back": {"type": "string"},
                },
                "required": ["front", "back"],
            },
        }
    },
    "required": ["cards"],
}

MAX_CARDS = 4
#: A rating from the in-chat deck, the same four the review screen uses.
RATINGS = {
    1: fsrs.Rating.AGAIN,
    2: fsrs.Rating.HARD,
    3: fsrs.Rating.GOOD,
    4: fsrs.Rating.EASY,
}
RATING_SCORES = {1: 0.0, 2: 0.6, 3: 0.85, 4: 1.0}


def should_card(state: StudentConceptState, *, understood: bool) -> bool:
    """Once per concept, after it landed or the lesson moved on from it."""
    return state.cards_count == 0 and (understood or state.evidence_count >= 1)


def parse_cards(payload: dict[str, Any]) -> list[tuple[str, str]]:
    raw = payload.get("cards")
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        front = _text(item.get("front"))[:600]
        back = _text(item.get("back"))[:1200]
        key = front.lower()
        if front and back and key not in seen and front.lower() != back.lower():
            seen.add(key)
            out.append((front, back))
        if len(out) >= MAX_CARDS:
            break
    return out


async def generate_for_concept(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
    journey: LearningJourney,
    concept: str,
    context: str,
    gateway: AIGateway,
    model: str | None,
    now: datetime | None = None,
) -> list[Card]:
    """Two to four atomic cards for one concept, from what the lesson said.

    A failed call returns no cards and the lesson continues (the brief's
    fallback rule); the concept stays eligible for the next opportunity.
    """
    now = now or utcnow()
    prompt = load("professor.flashcards")
    user = (
        f"Subject: {journey.subject}\nConcept: {concept}\n"
        f"Language: {journey.profile.get('language') or 'the language of the lesson'}\n\n"
        f"<LESSON>\n{context[:6000]}\n</LESSON>"
    )
    try:
        payload = await gateway.structured(
            StructuredRequest(
                messages=[
                    Message(role=Role.SYSTEM, content=prompt.body),
                    Message(role=Role.USER, content=user),
                ],
                json_schema=CARDS_SCHEMA,
                task=TaskClass.GENERATE_CARDS,
                model=model,
                metadata={"feature": "professor.flashcards"},
            )
        )
    except ProviderError as exc:
        log.warning("professor.flashcards_failed", concept=concept, error=str(exc))
        return []

    pairs = parse_cards(payload)
    if not pairs:
        return []
    cards = [
        Card(
            owner_id=owner_id,
            notebook_id=journey.notebook_id,
            journey_id=journey.id,
            concept_name=concept[:200],
            type=CardType.BASIC,
            front_md=front,
            back_md=back,
            origin=CardOrigin.AI,
            source_chunk_ids=[],
        )
        for front, back in pairs
    ]
    db.add_all(cards)
    await db.flush()

    student = StudentModel(db, owner_id, journey)
    state = await student.ensure(concept)
    state.cards_count += len(cards)
    await db.flush()
    log.info("professor.flashcards_created", concept=concept, count=len(cards))
    return cards


async def recall(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
    journey: LearningJourney,
    card_id: uuid.UUID,
    rating: int,
    elapsed_ms: int = 0,
    target_retention: float = 0.9,
    weights: fsrs.Weights = fsrs.DEFAULT_WEIGHTS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """The learner turned a lesson card over and graded themselves.

    Approves the card if this is its first reading, records the FSRS review
    (the same function the review screen uses) and a `flashcard` mastery
    event on the concept.
    """
    if rating not in RATINGS:
        raise NotFound("Unknown rating")
    now = now or utcnow()
    card = await db.scalar(
        select(Card).where(
            Card.id == card_id,
            Card.owner_id == owner_id,
            Card.journey_id == journey.id,
            Card.deleted_at.is_(None),
        )
    )
    if card is None:
        raise NotFound("Card not found")
    if card.approved_at is None:
        card.approved_at = now
        await db.flush()

    outcome = await record_review(
        db,
        card.id,
        owner_id=owner_id,
        rating=RATINGS[rating],
        elapsed_ms=elapsed_ms,
        target_retention=target_retention,
        weights=weights,
        now=now,
    )
    state = None
    if card.concept_name:
        student = StudentModel(db, owner_id, journey)
        state = await student.record(
            card.concept_name,
            kind="flashcard",
            score=RATING_SCORES[rating],
            detail={"card_id": str(card.id), "rating": rating},
            now=now,
        )
    return {
        "card_id": str(card.id),
        "due_at": outcome.due_at.isoformat(),
        "scheduled_days": round(outcome.scheduled_days, 3),
        "concept": card.concept_name,
        "state": state.state if state is not None else None,
    }


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""
