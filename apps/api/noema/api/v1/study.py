"""Cards, reviews and mastery."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import func, select

from noema.api.v1 import deps
from noema.core.errors import NotFound
from noema.db.base import utcnow
from noema.db.models import (
    Card,
    CardOrigin,
    CardSchedule,
    CardState,
    CardType,
    Concept,
    ConceptMastery,
    Notebook,
)
from noema.db.repository import OwnedRepository
from noema.engines import fsrs
from noema.study.review import record_review

router = APIRouter(tags=["study"], dependencies=[Depends(deps.require_csrf)])

MAX_BATCH = 200


class CardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    notebook_id: uuid.UUID
    concept_id: uuid.UUID | None
    type: CardType
    front_md: str
    back_md: str
    origin: CardOrigin
    approved_at: datetime | None
    source_chunk_ids: list[uuid.UUID]
    created_at: datetime


class DueCard(CardOut):
    due_at: datetime | None
    state: CardState
    reps: int


class CardCreate(BaseModel):
    notebook_id: uuid.UUID
    front_md: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    back_md: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    type: CardType = CardType.BASIC
    concept_id: uuid.UUID | None = None


class CardUpdate(BaseModel):
    front_md: Annotated[str, StringConstraints(min_length=1, max_length=500)] | None = (
        None
    )
    back_md: Annotated[str, StringConstraints(min_length=1, max_length=2000)] | None = (
        None
    )
    concept_id: uuid.UUID | None = None


class GenerateRequest(BaseModel):
    notebook_id: uuid.UUID
    limit: Annotated[int, Field(ge=1, le=50)] = 20


class ReviewIn(BaseModel):
    card_id: uuid.UUID
    rating: Annotated[int, Field(ge=1, le=4)]
    elapsed_ms: Annotated[int, Field(ge=0)] = 0
    #: Asked after the rating, and deliberately optional. It feeds mastery and
    #: misconception detection, never FSRS — the weights are fitted against a grade
    #: signal, and a second uncalibrated one would break that fit.
    confidence: Annotated[int, Field(ge=1, le=5)] | None = None


class ReviewOut(BaseModel):
    card_id: uuid.UUID
    due_at: datetime
    scheduled_days: float
    state: CardState
    mastery: float | None


class MasteryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    concept_id: uuid.UUID
    concept_name: str
    mastery: float
    provisional: bool
    components: dict[str, Any]
    last_evidence_at: datetime | None


class ForecastDay(BaseModel):
    date: str
    due: int


# ── Cards ─────────────────────────────────────────────────────────────────────


@router.get("/cards", response_model=list[DueCard])
async def list_cards(
    user: deps.CurrentUser,
    db: deps.SessionDep,
    notebook_id: uuid.UUID | None = None,
    due: bool = False,
    pending_approval: bool = False,
    limit: int = Query(default=50, le=MAX_BATCH),
) -> list[DueCard]:
    """List cards.

    ``due=true`` is the study queue: approved, unsuspended, and either never seen or
    past its due date, oldest first so the most overdue is answered first.
    """
    stmt = (
        select(Card, CardSchedule)
        .outerjoin(CardSchedule, CardSchedule.card_id == Card.id)
        .where(Card.owner_id == user.id, Card.deleted_at.is_(None))
    )

    if notebook_id is not None:
        stmt = stmt.where(Card.notebook_id == notebook_id)

    if pending_approval:
        stmt = stmt.where(Card.approved_at.is_(None))
    else:
        stmt = stmt.where(Card.approved_at.is_not(None), Card.suspended_at.is_(None))

    if due:
        stmt = stmt.where(
            (CardSchedule.due_at.is_(None)) | (CardSchedule.due_at <= utcnow())
        ).order_by(CardSchedule.due_at.asc().nullsfirst())
    else:
        stmt = stmt.order_by(Card.created_at.desc())

    rows = (await db.execute(stmt.limit(limit))).all()
    return [
        DueCard(
            **CardOut.model_validate(card).model_dump(),
            due_at=schedule.due_at if schedule else None,
            state=schedule.state if schedule else CardState.NEW,
            reps=schedule.reps if schedule else 0,
        )
        for card, schedule in rows
    ]


@router.post("/cards", response_model=CardOut, status_code=status.HTTP_201_CREATED)
async def create_card(
    payload: CardCreate, user: deps.CurrentUser, db: deps.SessionDep
) -> CardOut:
    await OwnedRepository(db, Notebook, user.id).get(payload.notebook_id)

    card = Card(
        owner_id=user.id,
        notebook_id=payload.notebook_id,
        concept_id=payload.concept_id,
        type=payload.type,
        front_md=payload.front_md,
        back_md=payload.back_md,
        origin=CardOrigin.USER,
        # A card the user wrote needs no approval; they just approved it by writing it.
        approved_at=utcnow(),
        source_chunk_ids=[],
    )
    db.add(card)
    await db.flush()
    return CardOut.model_validate(card)


@router.post("/cards/generate", response_model=list[CardOut])
async def generate(
    payload: GenerateRequest,
    user: deps.CurrentUser,
    db: deps.SessionDep,
    gateway: deps.GatewayDep,
    settings: deps.SettingsDep,
) -> list[CardOut]:
    """Draft cards from a notebook's material.

    They arrive unapproved. Nothing generated enters the rotation until a human has
    read it — spaced repetition is very good at making a wrong card permanent.
    """
    from noema.study.generation import generate_cards

    await OwnedRepository(db, Notebook, user.id).get(payload.notebook_id)

    cards = await generate_cards(
        db,
        payload.notebook_id,
        owner_id=user.id,
        gateway=gateway,
        limit=payload.limit,
        model=settings.noema_model_extract or None,
    )
    return [CardOut.model_validate(card) for card in cards]


@router.patch("/cards/{card_id}", response_model=CardOut)
async def update_card(
    card_id: uuid.UUID,
    payload: CardUpdate,
    user: deps.CurrentUser,
    db: deps.SessionDep,
) -> CardOut:
    card = await _card(db, user.id, card_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(card, field, value)
    await db.flush()
    return CardOut.model_validate(card)


@router.post("/cards/{card_id}/approve", response_model=CardOut)
async def approve_card(
    card_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> CardOut:
    card = await _card(db, user.id, card_id)
    if card.approved_at is None:
        card.approved_at = utcnow()
        await db.flush()
    return CardOut.model_validate(card)


@router.delete("/cards/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_card(
    card_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> None:
    card = await _card(db, user.id, card_id)
    card.deleted_at = utcnow()
    await db.flush()


# ── Reviews ───────────────────────────────────────────────────────────────────


@router.post("/reviews", response_model=ReviewOut)
async def submit_review(
    payload: ReviewIn,
    user: deps.CurrentUser,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
) -> ReviewOut:
    outcome = await record_review(
        db,
        payload.card_id,
        owner_id=user.id,
        rating=fsrs.Rating(payload.rating),
        elapsed_ms=payload.elapsed_ms,
        confidence=payload.confidence,
        target_retention=settings.noema_fsrs_target_retention,
    )
    return ReviewOut(
        card_id=outcome.card_id,
        due_at=outcome.due_at,
        scheduled_days=round(outcome.scheduled_days, 3),
        state=outcome.state,
        mastery=round(outcome.mastery, 2) if outcome.mastery is not None else None,
    )


@router.post("/reviews/batch", response_model=list[ReviewOut])
async def submit_reviews(
    payload: Annotated[list[ReviewIn], Field(max_length=MAX_BATCH)],
    user: deps.CurrentUser,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
) -> list[ReviewOut]:
    """Flush a queue of reviews taken offline.

    Applied in order, because each one's interval depends on the state the previous
    one left behind.
    """
    results: list[ReviewOut] = []
    for entry in payload:
        outcome = await record_review(
            db,
            entry.card_id,
            owner_id=user.id,
            rating=fsrs.Rating(entry.rating),
            elapsed_ms=entry.elapsed_ms,
            confidence=entry.confidence,
            target_retention=settings.noema_fsrs_target_retention,
        )
        results.append(
            ReviewOut(
                card_id=outcome.card_id,
                due_at=outcome.due_at,
                scheduled_days=round(outcome.scheduled_days, 3),
                state=outcome.state,
                mastery=round(outcome.mastery, 2)
                if outcome.mastery is not None
                else None,
            )
        )
    return results


@router.get("/reviews/forecast", response_model=list[ForecastDay])
async def forecast(
    user: deps.CurrentUser, db: deps.SessionDep, days: int = Query(default=30, le=180)
) -> list[ForecastDay]:
    """Upcoming workload, so a learner can see a wall before they hit it."""
    horizon = utcnow() + timedelta(days=days)
    rows = (
        await db.execute(
            select(func.date(CardSchedule.due_at), func.count())
            .join(Card, Card.id == CardSchedule.card_id)
            .where(
                CardSchedule.owner_id == user.id,
                CardSchedule.due_at <= horizon,
                Card.deleted_at.is_(None),
                Card.suspended_at.is_(None),
            )
            .group_by(func.date(CardSchedule.due_at))
            .order_by(func.date(CardSchedule.due_at))
        )
    ).all()
    return [ForecastDay(date=str(day), due=int(count)) for day, count in rows]


# ── Mastery ───────────────────────────────────────────────────────────────────


@router.get("/mastery", response_model=list[MasteryOut])
async def mastery(
    user: deps.CurrentUser,
    db: deps.SessionDep,
    workspace_id: uuid.UUID | None = None,
    weak: bool = False,
    limit: int = Query(default=100, le=500),
) -> list[MasteryOut]:
    """Mastery per concept, with the terms that produced each number."""
    stmt = (
        select(ConceptMastery, Concept.name)
        .join(Concept, Concept.id == ConceptMastery.concept_id)
        .where(ConceptMastery.owner_id == user.id)
    )
    if workspace_id is not None:
        stmt = stmt.where(Concept.workspace_id == workspace_id)
    if weak:
        # The threshold from docs/mastery-engine.md §7. Provisional scores are
        # excluded: two data points is not evidence of a weakness.
        stmt = stmt.where(ConceptMastery.mastery < 60, ConceptMastery.evidence_count >= 4)

    stmt = stmt.order_by(
        ConceptMastery.mastery.asc() if weak else Concept.name.asc()
    ).limit(limit)

    return [
        MasteryOut(
            concept_id=row.concept_id,
            concept_name=name,
            mastery=round(row.mastery, 1),
            provisional=bool(row.components.get("provisional", True)),
            components=row.components,
            last_evidence_at=row.last_evidence_at,
        )
        for row, name in (await db.execute(stmt)).all()
    ]


async def _card(db: deps.SessionDep, owner_id: uuid.UUID, card_id: uuid.UUID) -> Card:
    card = await db.scalar(
        select(Card).where(
            Card.id == card_id, Card.owner_id == owner_id, Card.deleted_at.is_(None)
        )
    )
    if card is None:
        raise NotFound("Card not found")
    return card
