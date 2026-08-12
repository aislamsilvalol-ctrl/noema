"""Cards, reviews and mastery."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
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
    Difficulty,
    Grader,
    Mistake,
    Notebook,
    Question,
    QuestionType,
)
from noema.db.repository import OwnedRepository
from noema.engines import fsrs
from noema.study.review import RELEARN_DELAY, record_review

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


class IntervalPreview(BaseModel):
    """What each answer would cost in time before the card returns."""

    again: float
    hard: float
    good: float
    easy: float


class DueCard(CardOut):
    due_at: datetime | None
    state: CardState
    reps: int
    #: Shown on the rating buttons. A learner choosing between "Hard" and "Good"
    #: deserves to know that one means three days and the other means three weeks.
    preview: IntervalPreview


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
    settings: deps.SettingsDep,
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
    retention = settings.noema_fsrs_target_retention
    return [
        DueCard(
            **CardOut.model_validate(card).model_dump(),
            due_at=schedule.due_at if schedule else None,
            state=schedule.state if schedule else CardState.NEW,
            reps=schedule.reps if schedule else 0,
            preview=_preview(schedule, retention),
        )
        for card, schedule in rows
    ]


def _preview(schedule: CardSchedule | None, target_retention: float) -> IntervalPreview:
    """The interval each rating would produce, in days.

    Computed with the same pure functions the review path uses, so the number the
    learner sees on the button is the number they get.
    """
    now = utcnow()
    before = (
        fsrs.MemoryState(stability=schedule.stability, difficulty=schedule.difficulty)
        if schedule is not None and schedule.reps > 0
        else None
    )
    elapsed = 0.0
    if schedule is not None and schedule.last_review_at is not None:
        last = schedule.last_review_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        elapsed = max((now - last).total_seconds() / 86400, 0.0)

    def interval(rating: fsrs.Rating) -> float:
        if rating is fsrs.Rating.AGAIN:
            return RELEARN_DELAY.total_seconds() / 86400
        state = fsrs.next_state(before, rating, elapsed)
        return round(fsrs.interval_days(state, target_retention), 3)

    return IntervalPreview(
        again=interval(fsrs.Rating.AGAIN),
        hard=interval(fsrs.Rating.HARD),
        good=interval(fsrs.Rating.GOOD),
        easy=interval(fsrs.Rating.EASY),
    )


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


# ── Questions ─────────────────────────────────────────────────────────────────


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    notebook_id: uuid.UUID
    concept_id: uuid.UUID | None
    type: QuestionType
    difficulty: Difficulty
    prompt: str
    #: The answer is not in here. An MCQ ships its options; `correct_index`,
    #: `accepted` and `answer` are stripped, because a question whose answer the
    #: client already holds tests nothing.
    payload: dict[str, Any]
    created_at: datetime


class AnswerIn(BaseModel):
    question_id: uuid.UUID
    response: dict[str, Any]
    confidence: Annotated[int, Field(ge=1, le=5)] | None = None
    elapsed_ms: Annotated[int, Field(ge=0)] = 0


class AnswerOut(BaseModel):
    id: uuid.UUID
    is_correct: bool
    score: float
    grader: Grader
    feedback: dict[str, Any] | None


class MistakeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    question_id: uuid.UUID
    concept_id: uuid.UUID | None
    prompt: str
    confidence: int | None
    is_misconception: bool
    created_at: datetime


#: Fields that would hand the learner the answer.
ANSWER_KEYS = {"correct_index", "answer", "accepted", "order"}


def _public_payload(question: Question) -> dict[str, Any]:
    return {k: v for k, v in question.payload.items() if k not in ANSWER_KEYS}


@router.get("/questions", response_model=list[QuestionOut])
async def list_questions(
    user: deps.CurrentUser,
    db: deps.SessionDep,
    notebook_id: uuid.UUID | None = None,
    concept_id: uuid.UUID | None = None,
    limit: int = Query(default=20, le=100),
) -> list[QuestionOut]:
    stmt = select(Question).where(
        Question.owner_id == user.id, Question.deleted_at.is_(None)
    )
    if notebook_id is not None:
        stmt = stmt.where(Question.notebook_id == notebook_id)
    if concept_id is not None:
        stmt = stmt.where(Question.concept_id == concept_id)

    rows = (
        await db.scalars(stmt.order_by(Question.created_at.desc()).limit(limit))
    ).all()
    return [
        QuestionOut(
            **{
                **QuestionOut.model_validate(row).model_dump(),
                "payload": _public_payload(row),
            }
        )
        for row in rows
    ]


@router.post("/questions/generate", response_model=list[QuestionOut])
async def generate_quiz(
    payload: GenerateRequest,
    user: deps.CurrentUser,
    db: deps.SessionDep,
    gateway: deps.GatewayDep,
    settings: deps.SettingsDep,
) -> list[QuestionOut]:
    from noema.study.questions import generate_questions

    await OwnedRepository(db, Notebook, user.id).get(payload.notebook_id)

    questions = await generate_questions(
        db,
        payload.notebook_id,
        owner_id=user.id,
        gateway=gateway,
        limit=payload.limit,
        model=settings.noema_model_extract or None,
    )
    return [
        QuestionOut(
            **{
                **QuestionOut.model_validate(q).model_dump(),
                "payload": _public_payload(q),
            }
        )
        for q in questions
    ]


@router.post("/answers", response_model=AnswerOut)
async def submit_answer(
    payload: AnswerIn,
    user: deps.CurrentUser,
    db: deps.SessionDep,
    gateway: deps.GatewayDep,
    settings: deps.SettingsDep,
) -> AnswerOut:
    """Grade an answer and record it as evidence."""
    from noema.study.questions import answer_question

    answer = await answer_question(
        db,
        payload.question_id,
        payload.response,
        owner_id=user.id,
        gateway=gateway,
        confidence=payload.confidence,
        elapsed_ms=payload.elapsed_ms,
        model=settings.noema_model_grade or None,
    )
    return AnswerOut(
        id=answer.id,
        is_correct=answer.is_correct,
        score=round(answer.score, 3),
        grader=answer.grader,
        feedback=answer.feedback,
    )


@router.get("/mistakes", response_model=list[MistakeOut])
async def list_mistakes(
    user: deps.CurrentUser,
    db: deps.SessionDep,
    unresolved: bool = True,
    misconceptions_only: bool = False,
    limit: int = Query(default=50, le=200),
) -> list[MistakeOut]:
    """The mistake bank.

    Misconceptions first: a confident wrong answer is the failure spaced repetition
    never catches, because the learner has no reason to flag it for review.
    """
    stmt = (
        select(Mistake, Question.prompt)
        .join(Question, Question.id == Mistake.question_id)
        .where(Mistake.owner_id == user.id)
    )
    if unresolved:
        stmt = stmt.where(Mistake.resolved_at.is_(None))
    if misconceptions_only:
        stmt = stmt.where(Mistake.is_misconception.is_(True))

    rows = (
        await db.execute(
            stmt.order_by(
                Mistake.is_misconception.desc(), Mistake.created_at.desc()
            ).limit(limit)
        )
    ).all()

    return [
        MistakeOut(
            id=mistake.id,
            question_id=mistake.question_id,
            concept_id=mistake.concept_id,
            prompt=prompt,
            confidence=mistake.confidence,
            is_misconception=mistake.is_misconception,
            created_at=mistake.created_at,
        )
        for mistake, prompt in rows
    ]


# ── Learning session ──────────────────────────────────────────────────────────


class PlanItem(BaseModel):
    ref_id: uuid.UUID
    kind: str
    concept_id: uuid.UUID | None
    concept_name: str
    estimated_seconds: float


class PlanBlockOut(BaseModel):
    kind: str
    #: Required, not decoration. If the engine cannot say why a block is there in one
    #: sentence, that is a bug in the engine rather than a gap in the response.
    why: str
    minutes: float
    items: list[PlanItem]


class PlanOut(BaseModel):
    rationale: str
    estimated_minutes: float
    blocks: list[PlanBlockOut]


@router.get("/learning-session/plan", response_model=PlanOut)
async def session_plan(
    user: deps.CurrentUser,
    db: deps.SessionDep,
    minutes: int = Query(default=30, ge=5, le=180),
) -> PlanOut:
    """What the next ``minutes`` should contain, and why.

    The user does not choose what to study — the engine decides from mastery,
    forgetting, prerequisites and recent mistakes, and explains itself.
    """
    from noema.study.session import plan_session

    plan = await plan_session(db, owner_id=user.id, minutes=minutes)

    return PlanOut(
        rationale=plan.rationale,
        estimated_minutes=round(plan.estimated_seconds / 60, 1),
        blocks=[
            PlanBlockOut(
                kind=block.kind.value,
                why=block.why,
                minutes=round(block.seconds / 60, 1),
                items=[
                    PlanItem(
                        ref_id=item.ref_id,
                        kind=item.kind.value,
                        concept_id=item.concept_id,
                        concept_name=item.concept_name,
                        estimated_seconds=round(item.cost_seconds, 1),
                    )
                    for item in block.items
                ],
            )
            for block in plan.blocks
        ],
    )
