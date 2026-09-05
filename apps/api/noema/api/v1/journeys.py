"""Learning journeys, lesson cards and in-lesson assessments (V3).

Read endpoints for what the Professor Engine writes during a turn, and the
two learner actions that happen outside the stream: turning a lesson card
over (`recall`) and handing in an assessment (`submit`). Both feed the
student model; neither calls the teaching model — the correction that
follows an assessment is the next Professor turn, asked for by the client
with a `learning_event` of kind `assessment`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from noema.api.v1 import deps
from noema.db.models import (
    Assessment,
    JourneyStatus,
    LearningJourney,
    MemorySummary,
    TeachingSession,
)
from noema.db.repository import OwnedRepository
from noema.professor import assessment as assessments
from noema.professor import flashcards
from noema.professor.engine import journey_public
from noema.professor.student import StudentModel
from noema.services.credentials import CredentialService
from noema.study.scheduling import fitted_weights

router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[Depends(deps.require_csrf)])


class JourneyConceptOut(BaseModel):
    name: str
    state: str
    evidence: int
    misconceptions: list[str]


class JourneyLessonOut(BaseModel):
    title: str
    status: str
    concepts: list[str]


class JourneyModuleOut(BaseModel):
    title: str
    status: str
    lessons: list[JourneyLessonOut]


class JourneyPositionOut(BaseModel):
    module: int
    lesson: int
    concept: str


class MemorySummaryOut(BaseModel):
    level: str
    turn_from: int
    turn_to: int
    summary: dict[str, Any]
    created_at: datetime


class JourneyOut(BaseModel):
    id: uuid.UUID
    subject: str
    objective: str
    level: str
    status: str
    plan: list[JourneyModuleOut]
    current: JourneyPositionOut
    checkpoints: int
    concepts: list[JourneyConceptOut]
    #: The latest open session on this journey, for "continue".
    session_id: uuid.UUID | None
    memory: list[MemorySummaryOut]


class RecallIn(BaseModel):
    rating: Annotated[int, Field(ge=1, le=4)]
    elapsed_ms: Annotated[int, Field(ge=0)] = 0


class RecallOut(BaseModel):
    card_id: uuid.UUID
    due_at: datetime
    scheduled_days: float
    concept: str | None
    state: str | None


class AssessmentQuestionOut(BaseModel):
    index: int
    type: str
    prompt: str
    concept: str
    options: list[str] | None = None
    items: list[str] | None = None


class AssessmentOut(BaseModel):
    id: uuid.UUID
    kind: str
    status: str
    title: str
    questions: list[AssessmentQuestionOut]
    score: float | None
    results: dict[str, Any]


class AssessmentSubmitIn(BaseModel):
    #: One entry per question, positional: an option index, a boolean, a
    #: string, or a list of strings for ordering. `null` for skipped.
    responses: Annotated[list[Any], Field(max_length=12)]


async def _journey(
    db: deps.SessionDep, user: deps.CurrentUser, journey_id: uuid.UUID
) -> LearningJourney:
    return await OwnedRepository(db, LearningJourney, user.id).get(journey_id)


async def _journey_out(
    db: deps.SessionDep, user: deps.CurrentUser, journey: LearningJourney
) -> JourneyOut:
    states = await StudentModel(db, user.id, journey).public()
    public = journey_public(journey, states)
    session_id = await db.scalar(
        select(TeachingSession.id)
        .where(
            TeachingSession.journey_id == journey.id,
            TeachingSession.owner_id == user.id,
            TeachingSession.ended_at.is_(None),
        )
        .order_by(TeachingSession.last_turn_at.desc().nulls_last())
        .limit(1)
    )
    summaries = await db.execute(
        select(MemorySummary)
        .where(
            MemorySummary.journey_id == journey.id,
            MemorySummary.owner_id == user.id,
            MemorySummary.superseded_at.is_(None),
        )
        .order_by(MemorySummary.created_at.desc())
        .limit(6)
    )
    return JourneyOut(
        id=journey.id,
        subject=public["subject"],
        objective=public["objective"],
        level=public["level"],
        status=public["status"],
        plan=[JourneyModuleOut.model_validate(m) for m in public["plan"]],
        current=JourneyPositionOut.model_validate(public["current"]),
        checkpoints=public["checkpoints"],
        concepts=[JourneyConceptOut.model_validate(c) for c in states],
        session_id=session_id,
        memory=[
            MemorySummaryOut(
                level=s.level,
                turn_from=s.turn_from,
                turn_to=s.turn_to,
                summary=s.summary,
                created_at=s.created_at,
            )
            for s in summaries.scalars()
        ],
    )


@router.get("/journeys/latest", response_model=JourneyOut | None)
async def latest_journey(
    user: deps.CurrentUser, db: deps.SessionDep, notebook_id: uuid.UUID | None = None
) -> JourneyOut | None:
    """The journey the learner was last on — the home screen's continue."""
    query = (
        select(LearningJourney)
        .where(
            LearningJourney.owner_id == user.id,
            LearningJourney.status == JourneyStatus.ACTIVE.value,
        )
        .order_by(LearningJourney.last_active_at.desc().nulls_last())
        .limit(1)
    )
    if notebook_id is not None:
        query = query.where(LearningJourney.notebook_id == notebook_id)
    journey = await db.scalar(query)
    if journey is None:
        return None
    return await _journey_out(db, user, journey)


@router.get("/journeys", response_model=list[JourneyOut])
async def list_journeys(user: deps.CurrentUser, db: deps.SessionDep) -> list[JourneyOut]:
    rows = await db.execute(
        select(LearningJourney)
        .where(LearningJourney.owner_id == user.id)
        .order_by(LearningJourney.last_active_at.desc().nulls_last())
        .limit(50)
    )
    return [await _journey_out(db, user, j) for j in rows.scalars()]


@router.get("/journeys/{journey_id}", response_model=JourneyOut)
async def get_journey(
    journey_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> JourneyOut:
    return await _journey_out(db, user, await _journey(db, user, journey_id))


@router.post("/journeys/{journey_id}/cards/{card_id}/recall", response_model=RecallOut)
async def recall_card(
    journey_id: uuid.UUID,
    card_id: uuid.UUID,
    payload: RecallIn,
    user: deps.CurrentUser,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
) -> RecallOut:
    """A lesson card turned over and graded — approves it on first reading,
    records the FSRS review and a mastery event."""
    journey = await _journey(db, user, journey_id)
    outcome = await flashcards.recall(
        db,
        owner_id=user.id,
        journey=journey,
        card_id=card_id,
        rating=payload.rating,
        elapsed_ms=payload.elapsed_ms,
        target_retention=settings.noema_fsrs_target_retention,
        weights=fitted_weights(user),
    )
    return RecallOut(
        card_id=uuid.UUID(outcome["card_id"]),
        due_at=datetime.fromisoformat(outcome["due_at"]),
        scheduled_days=outcome["scheduled_days"],
        concept=outcome["concept"],
        state=outcome["state"],
    )


@router.get("/assessments/{assessment_id}", response_model=AssessmentOut)
async def get_assessment(
    assessment_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> AssessmentOut:
    assessment = await OwnedRepository(db, Assessment, user.id).get(assessment_id)
    return AssessmentOut.model_validate(assessments.public_view(assessment))


@router.post("/assessments/{assessment_id}/submit", response_model=AssessmentOut)
async def submit_assessment(
    assessment_id: uuid.UUID,
    payload: AssessmentSubmitIn,
    user: deps.CurrentUser,
    db: deps.SessionDep,
    gateway: deps.GatewayDep,
    settings: deps.SettingsDep,
    box: deps.SecretBoxDep,
) -> AssessmentOut:
    """Hand the paper in. Closed questions are graded here and now; open ones
    by the rubric grader on the economy tier. The results feed the student
    model; the correction is the next Professor turn."""
    assessment = await OwnedRepository(db, Assessment, user.id).get(assessment_id)
    journey = await _journey(db, user, assessment.journey_id)
    from noema.api.v1.deps import build_provider
    from noema.db.models import ModelTier
    from noema.services.professor import tiered_gateway

    economy = await tiered_gateway(
        ModelTier.ECONOMY,
        db=db,
        default_gateway=gateway,
        build_provider=build_provider,
        settings=settings,
        credentials=CredentialService(db, box, user.id),
    )
    graded = await assessments.submit(
        db,
        owner_id=user.id,
        journey=journey,
        assessment_id=assessment.id,
        responses=payload.responses,
        gateway=economy.gateway,
        model=economy.model,
    )
    return AssessmentOut.model_validate(assessments.public_view(graded))
