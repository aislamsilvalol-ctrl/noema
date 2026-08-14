"""Cards, reviews and mastery."""

from __future__ import annotations

import hashlib
import random
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.api.v1 import deps
from noema.core.config import get_settings
from noema.core.errors import Conflict, NotFound
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
    Exam,
    Goal,
    Grader,
    Mistake,
    Notebook,
    Question,
    QuestionType,
    StudySession,
)
from noema.db.repository import OwnedRepository
from noema.engines import fsrs
from noema.study.review import RELEARN_DELAY, record_review
from noema.study.scheduling import fitted_weights

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
    # The intervals on the buttons have to be the ones that will actually be
    # applied, so the preview is computed with the same weights as the review.
    weights = fitted_weights(user)
    return [
        DueCard(
            **CardOut.model_validate(card).model_dump(),
            due_at=schedule.due_at if schedule else None,
            state=schedule.state if schedule else CardState.NEW,
            reps=schedule.reps if schedule else 0,
            preview=_preview(schedule, retention, weights),
        )
        for card, schedule in rows
    ]


def _preview(
    schedule: CardSchedule | None,
    target_retention: float,
    weights: fsrs.Weights = fsrs.DEFAULT_WEIGHTS,
) -> IntervalPreview:
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
        state = fsrs.next_state(before, rating, elapsed, weights)
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

    if payload.type is CardType.REVERSE:
        # The mirror is a second row with its own schedule, not a flag on this
        # one. Recognising "diastole → filling phase" is a different memory from
        # producing "filling phase → diastole", and one schedule for both would
        # keep asking the easy direction and call the pair learned.
        db.add(
            Card(
                owner_id=user.id,
                notebook_id=payload.notebook_id,
                concept_id=payload.concept_id,
                type=CardType.REVERSE,
                front_md=payload.back_md,
                back_md=payload.front_md,
                origin=CardOrigin.USER,
                approved_at=utcnow(),
                source_chunk_ids=[],
            )
        )
    await db.flush()
    return CardOut.model_validate(card)


class ClozeCreate(BaseModel):
    notebook_id: uuid.UUID
    concept_id: uuid.UUID | None = None
    #: Text with `{{c1::…}}` deletions. One card is stored per deletion number.
    text: str
    #: Also make the mirror card for a two-sided fact — see `reverse` below.
    reverse: bool = False


@router.post(
    "/cards/cloze", response_model=list[CardOut], status_code=status.HTTP_201_CREATED
)
async def create_cloze(
    payload: ClozeCreate, user: deps.CurrentUser, db: deps.SessionDep
) -> list[CardOut]:
    """Turn one passage into one card per deletion.

    Separate rows rather than one card with several blanks: each deletion gets its
    own schedule, because recalling one says nothing about the others and pairing
    them lets a known half carry an unknown one indefinitely.
    """
    from noema.engines.cloze import expand

    await OwnedRepository(db, Notebook, user.id).get(payload.notebook_id)

    expanded = expand(payload.text)
    if not expanded:
        raise Conflict(
            "There is no deletion in that text. Wrap what should be hidden in "
            "{{c1::…}} — a cloze card with no blank would mark itself right forever."
        )

    cards = [
        Card(
            owner_id=user.id,
            notebook_id=payload.notebook_id,
            concept_id=payload.concept_id,
            type=CardType.CLOZE,
            front_md=item.front,
            back_md=item.back,
            origin=CardOrigin.USER,
            approved_at=utcnow(),
            source_chunk_ids=[],
        )
        for item in expanded
    ]
    for card in cards:
        db.add(card)
    await db.flush()

    return [CardOut.model_validate(card) for card in cards]


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
        weights=fitted_weights(user),
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
#: Fields that would hand the learner the answer. `pairs` is here because a
#: matching question stores the correct mapping under it — shipping that was
#: handing over the answer key with the question.
ANSWER_KEYS = {"correct_index", "answer", "accepted", "order", "pairs"}


def _public_payload(question: Question) -> dict[str, Any]:
    """What the client may see: everything needed to answer, nothing that answers.

    Stripping alone is not enough for the arrangement types. An ordering question
    keeps its answer *in* the thing to be rendered — remove `order` and there is
    nothing left to put in order. So the items are sent shuffled, and the shuffle
    is seeded by the question id: a reload must not rearrange work in progress.
    """
    public = {k: v for k, v in question.payload.items() if k not in ANSWER_KEYS}

    if question.type is QuestionType.ORDERING:
        public["items"] = _shuffled(question.payload.get("order", []), question.id)

    if question.type is QuestionType.MATCHING:
        pairs = question.payload.get("pairs", {})
        if isinstance(pairs, dict):
            public["left"] = list(pairs.keys())
            public["right"] = _shuffled(list(pairs.values()), question.id)

    return public


def _shuffled(items: Any, question_id: uuid.UUID) -> list[Any]:
    """A stable permutation of ``items`` for this question.

    Seeded from the deployment secret keyed by the question id, not from the id
    alone. The id is public: seed with it and a client can reproduce the
    permutation, invert it, and read back the order it was supposed to work out —
    which is the whole answer to an ordering question.

    Stable so a reload does not rearrange work in progress.
    """
    if not isinstance(items, list):
        return []

    digest = hashlib.blake2b(
        question_id.bytes, key=get_settings().session_secret_bytes, digest_size=16
    ).digest()

    shuffled = list(items)
    random.Random(int.from_bytes(digest)).shuffle(shuffled)  # noqa: S311 — presentation order, not a secret
    return shuffled


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


@router.get("/questions/{question_id}", response_model=QuestionOut)
async def get_question(
    question_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> QuestionOut:
    """One question, without its answer.

    The mistake bank needs this: it stores question ids, and re-asking one is the
    only thing that turns a list of failures into practice.
    """
    question = await OwnedRepository(db, Question, user.id).get(question_id)
    return QuestionOut(
        **{
            **QuestionOut.model_validate(question).model_dump(),
            "payload": _public_payload(question),
        }
    )


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


class SessionStart(BaseModel):
    minutes: Annotated[int, Field(ge=5, le=180)] = 30


class SessionOut(BaseModel):
    id: uuid.UUID
    planned_minutes: int
    estimated_minutes: float
    items_planned: int
    rationale: str


class SessionComplete(BaseModel):
    items_completed: Annotated[int, Field(ge=0)] = 0
    seconds: Annotated[float, Field(ge=0)] = 0


class CalibrationOut(BaseModel):
    """How honest the system's own numbers have been."""

    memory_model: dict[str, Any]
    planner: dict[str, Any]


@router.post("/learning-session/start", response_model=SessionOut)
async def start_session(
    payload: SessionStart, user: deps.CurrentUser, db: deps.SessionDep
) -> SessionOut:
    """Build a plan and store it.

    The plan is kept verbatim so a later scheduler change can be replayed against
    what this one actually decided.
    """
    from noema.study.session import plan_session, summarise

    plan = await plan_session(db, owner_id=user.id, minutes=payload.minutes)

    record = StudySession(
        owner_id=user.id,
        planned_minutes=payload.minutes,
        estimated_seconds=plan.estimated_seconds,
        rationale=plan.rationale,
        plan=summarise(plan),
        items_planned=len(plan.items),
        items_completed=0,
    )
    db.add(record)
    await db.flush()

    return SessionOut(
        id=record.id,
        planned_minutes=payload.minutes,
        estimated_minutes=round(plan.estimated_seconds / 60, 1),
        items_planned=len(plan.items),
        rationale=plan.rationale,
    )


@router.post("/learning-session/{session_id}/complete", response_model=SessionOut)
async def complete_session(
    session_id: uuid.UUID,
    payload: SessionComplete,
    user: deps.CurrentUser,
    db: deps.SessionDep,
) -> SessionOut:
    """Record what actually happened, which is the other half of the comparison."""
    record = await db.scalar(
        select(StudySession).where(
            StudySession.id == session_id, StudySession.owner_id == user.id
        )
    )
    if record is None:
        raise NotFound("Session not found")

    record.items_completed = min(payload.items_completed, record.items_planned)
    record.actual_seconds = payload.seconds
    record.completed_at = utcnow()
    await db.flush()

    return SessionOut(
        id=record.id,
        planned_minutes=record.planned_minutes,
        estimated_minutes=round(record.estimated_seconds / 60, 1),
        items_planned=record.items_planned,
        rationale=record.rationale,
    )


class ExamStart(BaseModel):
    notebook_id: uuid.UUID
    questions: Annotated[int, Field(ge=3, le=50)] = 10
    minutes: Annotated[int, Field(ge=1, le=180)] = 20


class ExamOut(BaseModel):
    id: uuid.UUID
    notebook_id: uuid.UUID
    minutes: int
    started_at: datetime
    submitted_at: datetime | None
    score: float | None
    overtime: bool
    results: dict[str, Any]
    questions: list[QuestionOut]


class ExamSubmit(BaseModel):
    #: Question id to response body, the same shapes `/answers` takes. Missing
    #: entries are graded as unanswered rather than dropped.
    answers: dict[uuid.UUID, dict[str, Any]]


async def _exam_out(db: AsyncSession, exam: Exam, owner_id: uuid.UUID) -> ExamOut:
    ids = [uuid.UUID(str(i)) for i in exam.question_ids]
    rows = (
        await db.scalars(
            select(Question).where(Question.owner_id == owner_id, Question.id.in_(ids))
        )
    ).all()
    by_id = {row.id: row for row in rows}

    return ExamOut(
        id=exam.id,
        notebook_id=exam.notebook_id,
        minutes=exam.minutes,
        started_at=exam.started_at,
        submitted_at=exam.submitted_at,
        score=exam.score,
        overtime=exam.overtime,
        results=exam.results,
        # In the stored order, so the paper is the same on a reload.
        questions=[
            QuestionOut(
                **{
                    **QuestionOut.model_validate(by_id[qid]).model_dump(),
                    "payload": _public_payload(by_id[qid]),
                }
            )
            for qid in ids
            if qid in by_id
        ],
    )


@router.post("/exams", response_model=ExamOut, status_code=status.HTTP_201_CREATED)
async def start_exam_endpoint(
    payload: ExamStart, user: deps.CurrentUser, db: deps.SessionDep
) -> ExamOut:
    """Sit an exam over one notebook.

    The questions are fixed here and the clock starts here, so reloading the page
    does not hand out a fresh, easier paper.
    """
    from noema.study.exam import start_exam

    await OwnedRepository(db, Notebook, user.id).get(payload.notebook_id)
    exam = await start_exam(
        db,
        payload.notebook_id,
        owner_id=user.id,
        count=payload.questions,
        minutes=payload.minutes,
    )
    return await _exam_out(db, exam, user.id)


@router.get("/exams/{exam_id}", response_model=ExamOut)
async def get_exam(
    exam_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> ExamOut:
    exam = await OwnedRepository(db, Exam, user.id).get(exam_id)
    return await _exam_out(db, exam, user.id)


@router.post("/exams/{exam_id}/submit", response_model=ExamOut)
async def submit_exam(
    exam_id: uuid.UUID,
    payload: ExamSubmit,
    user: deps.CurrentUser,
    db: deps.SessionDep,
    gateway: deps.GatewayDep,
    settings: deps.SettingsDep,
) -> ExamOut:
    """Hand in the paper. Everything is graded at once, and only now."""
    from noema.study.exam import grade_exam

    exam = await grade_exam(
        db,
        exam_id,
        payload.answers,
        owner_id=user.id,
        gateway=gateway,
        model=settings.noema_model_grade or None,
    )
    return await _exam_out(db, exam, user.id)


class ExplanationIn(BaseModel):
    concept_id: uuid.UUID
    text: str


class ExplanationOut(BaseModel):
    id: uuid.UUID
    concept_id: uuid.UUID
    score: float
    findings: dict[str, Any]
    explained_at: datetime


@router.post(
    "/explanations",
    response_model=ExplanationOut,
    status_code=status.HTTP_201_CREATED,
)
async def explain_concept(
    payload: ExplanationIn,
    user: deps.CurrentUser,
    db: deps.SessionDep,
    gateway: deps.GatewayDep,
    settings: deps.SettingsDep,
) -> ExplanationOut:
    """Feynman mode: explain a concept and be told what the explanation is missing.

    Judged against the learner's own material rather than the model's knowledge,
    and recorded as evidence — explaining unaided is the hardest retrieval there
    is, so it should move the number.
    """
    from noema.study.feynman import evaluate_explanation

    explanation = await evaluate_explanation(
        db,
        payload.concept_id,
        payload.text,
        owner_id=user.id,
        gateway=gateway,
        model=settings.noema_model_grade or None,
    )
    return ExplanationOut(
        id=explanation.id,
        concept_id=explanation.concept_id,
        score=round(explanation.score, 3),
        findings=explanation.findings,
        explained_at=explanation.explained_at,
    )


class SocraticIn(BaseModel):
    concept_id: uuid.UUID
    #: The dialogue so far, oldest first: {"role": "learner"|"tutor", "content": …}.
    #: Held by the client because a half-finished dialogue is not worth a table.
    transcript: list[dict[str, str]] = []


class SocraticOut(BaseModel):
    question: str
    reached: bool
    score: float
    assessment: str
    explanation_id: uuid.UUID | None
    exhausted: bool


@router.post("/socratic", response_model=SocraticOut)
async def socratic_turn(
    payload: SocraticIn,
    user: deps.CurrentUser,
    db: deps.SessionDep,
    gateway: deps.GatewayDep,
    settings: deps.SettingsDep,
) -> SocraticOut:
    """One turn of a Socratic dialogue: the next question, or the verdict.

    Unlike the tutor's Socratic mode this one concludes and records what was
    reached, because arriving at an idea under questioning is something the
    learner did.
    """
    from noema.study.socratic import next_turn

    turn = await next_turn(
        db,
        payload.concept_id,
        payload.transcript,
        owner_id=user.id,
        gateway=gateway,
        model=settings.noema_model_tutor or None,
    )
    return SocraticOut(
        question=turn.question,
        reached=turn.reached,
        score=round(turn.score, 3),
        assessment=turn.assessment,
        explanation_id=turn.explanation_id,
        exhausted=turn.exhausted,
    )


class DrillsOut(BaseModel):
    #: What the learner appears to believe, in their terms.
    belief: str
    questions: list[QuestionOut]


@router.post("/mistakes/{mistake_id}/drills", response_model=DrillsOut)
async def write_drills(
    mistake_id: uuid.UUID,
    user: deps.CurrentUser,
    db: deps.SessionDep,
    gateway: deps.GatewayDep,
    settings: deps.SettingsDep,
) -> DrillsOut:
    """Write questions that break the belief behind a confident wrong answer.

    Not the same question again: someone holding a coherent wrong model answers
    it the same way, and learns that one question rather than changing the model.
    """
    from noema.study.correction import build_drills

    drills = await build_drills(
        db,
        mistake_id,
        owner_id=user.id,
        gateway=gateway,
        model=settings.noema_model_extract or None,
    )
    return DrillsOut(
        belief=drills.belief,
        questions=[
            QuestionOut(
                **{
                    **QuestionOut.model_validate(q).model_dump(),
                    "payload": _public_payload(q),
                }
            )
            for q in drills.questions
        ],
    )


class GoalCreate(BaseModel):
    notebook_id: uuid.UUID
    title: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    due_on: date
    target_mastery: Annotated[float, Field(ge=1, le=100)] = 80.0
    minutes_per_day: Annotated[int, Field(ge=5, le=480)] = 30


class MilestoneOut(BaseModel):
    concept_id: uuid.UUID
    name: str
    from_mastery: float
    to_mastery: float
    estimated_minutes: float
    day: int


class GoalOut(BaseModel):
    id: uuid.UUID
    notebook_id: uuid.UUID
    title: str
    due_on: date
    target_mastery: float
    minutes_per_day: int
    days_left: int
    achieved_at: datetime | None
    reachable: bool
    projected_mastery: float
    required_minutes_per_day: float
    summary: str
    milestones: list[MilestoneOut]


async def _goal_out(db: AsyncSession, goal_id: uuid.UUID, owner_id: uuid.UUID) -> GoalOut:
    from noema.study.goals import achieved, days_remaining, path_for

    goal, path = await path_for(db, goal_id, owner_id=owner_id)
    goal.achieved_at = achieved(goal, path)

    return GoalOut(
        id=goal.id,
        notebook_id=goal.notebook_id,
        title=goal.title,
        due_on=goal.due_on,
        target_mastery=goal.target_mastery,
        minutes_per_day=goal.minutes_per_day,
        days_left=days_remaining(goal.due_on),
        achieved_at=goal.achieved_at,
        reachable=path.feasibility.reachable,
        projected_mastery=path.feasibility.projected_mastery,
        required_minutes_per_day=path.feasibility.required_minutes_per_day,
        summary=path.feasibility.summary,
        milestones=[MilestoneOut(**vars(m)) for m in path.milestones],
    )


@router.post("/goals", response_model=GoalOut, status_code=status.HTTP_201_CREATED)
async def create_goal(
    payload: GoalCreate, user: deps.CurrentUser, db: deps.SessionDep
) -> GoalOut:
    """Set something to know by a date.

    The path is not stored with it: it is recomputed on every read, because a plan
    pinned at creation describes a learner who no longer exists by Wednesday.
    """
    await OwnedRepository(db, Notebook, user.id).get(payload.notebook_id)

    goal = Goal(
        owner_id=user.id,
        notebook_id=payload.notebook_id,
        title=payload.title,
        due_on=payload.due_on,
        target_mastery=payload.target_mastery,
        minutes_per_day=payload.minutes_per_day,
    )
    db.add(goal)
    await db.flush()
    return await _goal_out(db, goal.id, user.id)


@router.get("/goals", response_model=list[GoalOut])
async def list_goals(user: deps.CurrentUser, db: deps.SessionDep) -> list[GoalOut]:
    """Soonest first — a deadline further away is not the one to look at."""
    rows = (
        await db.scalars(
            select(Goal).where(Goal.owner_id == user.id).order_by(Goal.due_on)
        )
    ).all()
    return [await _goal_out(db, goal.id, user.id) for goal in rows]


@router.get("/goals/{goal_id}", response_model=GoalOut)
async def get_goal(
    goal_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> GoalOut:
    return await _goal_out(db, goal_id, user.id)


@router.delete("/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(
    goal_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> None:
    await OwnedRepository(db, Goal, user.id).delete(goal_id)


class FitOut(BaseModel):
    adopted: bool
    baseline_loss: float
    candidate_loss: float
    train_attempts: int
    validation_attempts: int
    summary: str


@router.post("/analytics/fit-schedule", response_model=FitOut)
async def fit_schedule(
    user: deps.CurrentUser, db: deps.SessionDep, settings: deps.SettingsDep
) -> FitOut:
    """Fit the memory model to this learner's own review history.

    The default parameters were fitted on a large public dataset. They are a good
    prior and they are not you. This searches for better ones on the earlier half
    of your history and judges them on the later half, adopting them only if they
    win on reviews the search never saw.
    """
    from noema.engines.fsrs_optimize import optimise
    from noema.study.evaluation import attempts_for
    from noema.study.scheduling import store_weights

    fit = optimise(
        await attempts_for(db, owner_id=user.id),
        min_reviews=settings.noema_fsrs_optimize_min_reviews,
    )

    if fit.adopted:
        store_weights(
            user,
            fit.weights,
            {
                "fitted_at": utcnow().isoformat(),
                "log_loss": fit.candidate_loss,
                "baseline_log_loss": fit.baseline_loss,
                "reviews": fit.train_attempts + fit.validation_attempts,
            },
        )
        await db.flush()

    return FitOut(
        adopted=fit.adopted,
        baseline_loss=fit.baseline_loss,
        candidate_loss=fit.candidate_loss,
        train_attempts=fit.train_attempts,
        validation_attempts=fit.validation_attempts,
        summary=fit.summary,
    )


@router.get("/analytics/calibration", response_model=CalibrationOut)
async def calibration(user: deps.CurrentUser, db: deps.SessionDep) -> CalibrationOut:
    """Whether the system's own predictions have been honest.

    Published rather than kept internal on purpose: a tool that tells you when to
    study should be able to show whether it has been right.
    """
    from noema.study.evaluation import (
        evaluate_memory_model,
        evaluate_planner,
        has_enough_history,
    )

    memory = await evaluate_memory_model(db, owner_id=user.id)
    planner = await evaluate_planner(db, owner_id=user.id)

    return CalibrationOut(
        memory_model={
            "reviews_scored": memory.attempts,
            "predicted_recall": round(memory.mean_predicted, 3),
            "actual_recall": round(memory.actual_recall, 3),
            "calibration_error": round(memory.calibration_error, 3),
            "log_loss": round(memory.log_loss, 4),
            "reliable": has_enough_history(memory),
            "summary": memory.summary(),
            "curve": [
                {
                    "predicted": round(b.predicted, 3),
                    "actual": round(b.actual, 3),
                    "count": b.count,
                }
                for b in memory.buckets
            ],
        },
        planner={
            "sessions": planner.sessions,
            "estimated_minutes": planner.mean_estimated_minutes,
            "actual_minutes": planner.mean_actual_minutes,
            "completion_rate": planner.completion_rate,
            "summary": planner.summary(),
        },
    )
