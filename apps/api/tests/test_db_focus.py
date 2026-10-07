"""Modo TDAH against the real database: the next activity, focus sittings,
and the proof that a focus sitting moves the same knowledge state as normal
mode — because it calls the same endpoints.

Routes are called directly as coroutines, like the rest of this suite; the
Professor runs on a scripted mock provider and spends no token.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from noema.api.v1 import focus as routes
from noema.api.v1.ai import professor_chat
from noema.api.v1.schemas import (
    ChatIn,
    ChatMessageIn,
    FocusStartIn,
    FocusStepIn,
    LearningEventIn,
)
from noema.api.v1.study import ReviewIn, submit_review
from noema.core.config import Settings
from noema.core.crypto import SecretBox
from noema.core.errors import Conflict, NotFound
from noema.db.base import utcnow
from noema.db.models import (
    Card,
    CardOrigin,
    CardSchedule,
    FocusSession,
    LearningJourney,
    MasteryEvent,
    ModelTier,
    ModelTierConfig,
    StudentConceptState,
    TeachingSession,
    TeachingTurn,
    User,
)
from noema.providers.base import ChatRequest, StreamEvent, StructuredRequest, Usage
from noema.providers.gateway import AIGateway
from noema.providers.mock import MockProvider
from noema.services.focus_sessions import GoalRequired
from noema.services.progression import ProgressionEngine
from noema.services.usage import UsageWriter

pytestmark = pytest.mark.asyncio

PLAN = {
    "modules": [
        {
            "title": "Fundamentos",
            "lessons": [
                {"title": "O inconsciente", "concepts": ["inconsciente", "lapso"]},
            ],
        }
    ]
}
GOAL = {
    "subject": "Psicanálise freudiana",
    "objective": "Entender Freud do zero",
    "inferred_level": "introductory",
    "desired_depth": "foundational",
    "prerequisites": [],
    "language": "pt",
}
RECORD = (
    '{"subject": "Freud", "current_topic": "aparelho psíquico", '
    '"current_concept": "inconsciente", "learner_level": "introductory", '
    '"strategy": "analogy", "situation": "first_contact", "next_action": "check", '
    '"mastery_evidence": {"concept": "lapso", "verdict": "understood", '
    '"strength": "moderate"}, "plan": [{"topic": "inconsciente", "status": "current"}]}'
)
REPLY = (
    "Pensa no lapso. O que sobra embaixo da água?\n<PEDAGOGY>" + RECORD + "</PEDAGOGY>"
)
QUIZ = {
    "tool": "quiz",
    "data": {
        "question": "Onde?",
        "options": ["Guardado", "Sumiu"],
        "answer": 0,
        "concept": "inconsciente",
    },
}


class Scripted(MockProvider):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[ChatRequest] = []

    async def structured(self, request: StructuredRequest) -> dict[str, Any]:
        feature = request.metadata.get("feature", "")
        if feature == "professor.parse_goal":
            return GOAL
        if feature == "professor.curriculum":
            return PLAN
        if feature == "professor.route":
            return {"signal": "neutral"}
        if feature == "professor.flashcards":
            return {"cards": []}
        return await super().structured(request)

    async def stream(self, request: ChatRequest) -> Any:
        self.requests.append(request)
        for word in REPLY.split(" "):
            yield StreamEvent(delta=word + " ")
        yield StreamEvent(done=True, usage=Usage(prompt_tokens=100, completion_tokens=20))


async def _mock_tiers(db: AsyncSession) -> None:
    for tier in ModelTier:
        config = await db.get(ModelTierConfig, tier)
        assert config is not None
        config.provider = "mock"
        config.model = "mock-model"
    await db.flush()


def _patch(monkeypatch: pytest.MonkeyPatch, provider: MockProvider) -> None:
    async def build(name: str, settings_: Settings, credentials: Any) -> Any:
        return provider

    monkeypatch.setattr("noema.api.v1.deps.build_provider", build)


async def _turn(
    db: AsyncSession,
    user: User,
    settings: Settings,
    provider: MockProvider,
    text: str,
    *,
    session_id: uuid.UUID | None,
    focus: bool,
    event: LearningEventIn | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    response = await professor_chat(
        ChatIn(
            session_id=session_id,
            messages=[ChatMessageIn(role="user", content=text)],
            grounded=False,
            learning_event=event,
            focus=focus,
        ),
        user=user,
        db=db,
        gateway=AIGateway(provider, record_usage=UsageWriter(db, user.id)),
        settings=settings,
        box=SecretBox.from_base64(settings.noema_master_key),
    )
    events: list[tuple[str, dict[str, Any]]] = []
    async for chunk in response.body_iterator:
        text_ = chunk.decode() if isinstance(chunk, bytes) else str(chunk)
        for frame in text_.strip("\n").split("\n\n"):
            lines = frame.split("\n")
            events.append(
                (
                    lines[0].removeprefix("event: "),
                    json.loads(lines[1].removeprefix("data: ")),
                )
            )
    return events


async def _journey(db: AsyncSession, owner: User, **values: Any) -> LearningJourney:
    journey = LearningJourney(
        owner_id=owner.id,
        goal="Quero aprender Freud",
        subject="Freud",
        current_concept="recalque",
        plan=PLAN,
        last_active_at=utcnow(),
        **values,
    )
    db.add(journey)
    await db.flush()
    return journey


async def _cards(
    db: AsyncSession, owner: User, n: int, *, overdue: bool = False
) -> list[Card]:
    cards = []
    for i in range(n):
        card = Card(
            owner_id=owner.id,
            front_md=f"Pergunta {i}",
            back_md=f"Resposta {i}",
            origin=CardOrigin.USER,
            approved_at=utcnow(),
            source_chunk_ids=[],
        )
        db.add(card)
        await db.flush()
        if overdue:
            db.add(
                CardSchedule(
                    owner_id=owner.id,
                    card_id=card.id,
                    due_at=utcnow() - timedelta(days=3),
                )
            )
        cards.append(card)
    await db.flush()
    return cards


# ── the next activity ─────────────────────────────────────────────────────


async def test_a_new_account_is_told_to_start_something(
    db: AsyncSession, user: User
) -> None:
    activity = await routes.get_next_activity(user, db)
    assert activity.kind == "start"
    assert activity.due_count == 0


async def test_a_journey_under_way_is_continued_at_its_concept(
    db: AsyncSession, user: User
) -> None:
    journey = await _journey(db, user)
    user.settings = {"session_minutes": 8}
    activity = await routes.get_next_activity(user, db)
    assert activity.kind == "learn"
    assert activity.journey_id == journey.id
    assert activity.concept == "recalque"
    assert activity.minutes_estimate == 8
    assert activity.reason_code == "continue"


async def test_overdue_cards_come_before_the_journey(
    db: AsyncSession, user: User
) -> None:
    await _journey(db, user)
    await _cards(db, user, 2, overdue=True)
    activity = await routes.get_next_activity(user, db)
    assert activity.kind == "review"
    assert activity.due_count == 2
    assert activity.overdue_count == 2
    assert activity.reason == "2 cards overdue since yesterday or earlier"


async def test_another_users_cards_and_journeys_do_not_count(
    db: AsyncSession, user: User, other_user: User
) -> None:
    await _journey(db, other_user)
    await _cards(db, other_user, 9, overdue=True)
    activity = await routes.get_next_activity(user, db)
    assert activity.kind == "start"
    assert activity.due_count == 0


# ── focus sittings ────────────────────────────────────────────────────────


async def test_start_needs_a_goal_when_nothing_is_under_way(
    db: AsyncSession, user: User
) -> None:
    with pytest.raises(GoalRequired):
        await routes.start_focus_session(FocusStartIn(minutes=5), user, db)


async def test_a_goal_starts_a_learn_sitting_on_a_new_lesson(
    db: AsyncSession, user: User
) -> None:
    out = await routes.start_focus_session(
        FocusStartIn(minutes=5, goal="Quero aprender Freud"), user, db
    )
    assert out.kind == "learn"
    assert out.planned_minutes == 5
    assert out.steps_total == 2
    assert out.steps_done == 0
    assert out.status == "active"
    assert 290 <= out.seconds_left <= 300
    assert out.teaching_session_id is not None
    lesson = await db.get(TeachingSession, out.teaching_session_id)
    assert lesson is not None and lesson.owner_id == user.id
    assert lesson.learning_goal == "Quero aprender Freud"


async def test_a_journey_sitting_drives_that_journeys_lesson(
    db: AsyncSession, user: User
) -> None:
    journey = await _journey(db, user)
    out = await routes.start_focus_session(FocusStartIn(minutes=None), user, db)
    assert out.kind == "learn"
    assert out.journey_id == journey.id
    assert out.concept == "recalque"
    # Auto, for a lesson: ten minutes, four micro-steps.
    assert out.planned_minutes == 10
    assert out.steps_total == 4
    lesson = await db.get(TeachingSession, out.teaching_session_id)
    assert lesson is not None and lesson.journey_id == journey.id


async def test_a_review_sitting_counts_the_cards_it_can_hold(
    db: AsyncSession, user: User
) -> None:
    await _cards(db, user, 3, overdue=True)
    out = await routes.start_focus_session(FocusStartIn(minutes=None), user, db)
    assert out.kind == "review"
    assert out.planned_minutes == 5
    assert out.steps_total == 3
    assert out.teaching_session_id is None


async def test_one_open_sitting_per_learner(db: AsyncSession, user: User) -> None:
    first = await routes.start_focus_session(
        FocusStartIn(minutes=5, goal="Freud"), user, db
    )
    again = await routes.start_focus_session(
        FocusStartIn(minutes=25, goal="Outra coisa"), user, db
    )
    assert again.id == first.id
    assert again.planned_minutes == 5

    current = await routes.current_focus_session(user, db)
    assert current is not None and current.id == first.id

    # The database refuses a second open row even if the service is bypassed.
    now = utcnow()
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(
                FocusSession(
                    owner_id=user.id,
                    kind="learn",
                    planned_minutes=5,
                    steps_total=2,
                    status="paused",
                    started_at=now,
                    last_activity_at=now,
                )
            )


async def test_a_step_counts_once_and_never_skips(db: AsyncSession, user: User) -> None:
    out = await routes.start_focus_session(
        FocusStartIn(minutes=10, goal="Freud"), user, db
    )
    one = await routes.focus_step(out.id, FocusStepIn(index=0), user, db)
    assert one.steps_done == 1
    # A double click, a retried request: the same index, counted once.
    retry = await routes.focus_step(out.id, FocusStepIn(index=0), user, db)
    assert retry.steps_done == 1
    with pytest.raises(Conflict):
        await routes.focus_step(out.id, FocusStepIn(index=3), user, db)
    two = await routes.focus_step(out.id, FocusStepIn(index=1), user, db)
    assert two.steps_done == 2


async def test_pause_resume_complete(db: AsyncSession, user: User) -> None:
    out = await routes.start_focus_session(
        FocusStartIn(minutes=5, goal="Freud"), user, db
    )
    paused = await routes.pause_focus_session(out.id, user, db)
    assert paused.status == "paused" and paused.paused_at is not None
    # Pausing twice is the same pause.
    again = await routes.pause_focus_session(out.id, user, db)
    assert again.paused_at == paused.paused_at

    # Ten minutes away do not eat the five planned minutes.
    row = await db.get(FocusSession, out.id)
    assert row is not None and row.paused_at is not None
    row.paused_at = row.paused_at - timedelta(minutes=10)
    row.started_at = row.started_at - timedelta(minutes=10)
    await db.flush()
    resumed = await routes.resume_focus_session(out.id, user, db)
    assert resumed.status == "active" and resumed.paused_at is None
    assert 280 <= resumed.seconds_left <= 300
    assert row.paused_seconds >= 600

    done = await routes.complete_focus_session(out.id, user, db)
    assert done.status == "completed" and done.completed_at is not None
    # Completing twice is a no-op; anything else on an ended sitting is refused.
    assert (await routes.complete_focus_session(out.id, user, db)).status == "completed"
    with pytest.raises(Conflict):
        await routes.focus_step(out.id, FocusStepIn(index=0), user, db)
    with pytest.raises(Conflict):
        await routes.pause_focus_session(out.id, user, db)
    assert await routes.current_focus_session(user, db) is None


async def test_abandon_frees_the_slot_for_a_new_sitting(
    db: AsyncSession, user: User
) -> None:
    out = await routes.start_focus_session(
        FocusStartIn(minutes=5, goal="Freud"), user, db
    )
    gone = await routes.abandon_focus_session(out.id, user, db)
    assert gone.status == "abandoned"
    assert await routes.current_focus_session(user, db) is None
    fresh = await routes.start_focus_session(
        FocusStartIn(minutes=15, goal="Freud"), user, db
    )
    assert fresh.id != out.id


async def test_every_focus_route_is_404_for_another_user(
    db: AsyncSession, user: User, other_user: User
) -> None:
    out = await routes.start_focus_session(
        FocusStartIn(minutes=5, goal="Freud"), user, db
    )
    assert await routes.current_focus_session(other_user, db) is None
    with pytest.raises(NotFound):
        await routes.get_focus_session(out.id, other_user, db)
    with pytest.raises(NotFound):
        await routes.focus_step(out.id, FocusStepIn(index=0), other_user, db)
    with pytest.raises(NotFound):
        await routes.pause_focus_session(out.id, other_user, db)
    with pytest.raises(NotFound):
        await routes.resume_focus_session(out.id, other_user, db)
    with pytest.raises(NotFound):
        await routes.complete_focus_session(out.id, other_user, db)
    with pytest.raises(NotFound):
        await routes.abandon_focus_session(out.id, other_user, db)
    # And nothing they tried moved it.
    mine = await routes.get_focus_session(out.id, user, db)
    assert mine.status == "active" and mine.steps_done == 0


async def test_a_review_sitting_rates_through_the_ordinary_review_path(
    db: AsyncSession, user: User, settings: Settings
) -> None:
    cards = await _cards(db, user, 2, overdue=True)
    out = await routes.start_focus_session(FocusStartIn(minutes=5), user, db)
    for index, card in enumerate(cards):
        await submit_review(ReviewIn(card_id=card.id, rating=3), user, db, settings)
        await routes.focus_step(out.id, FocusStepIn(index=index), user, db)
    done = await routes.complete_focus_session(out.id, user, db)
    assert done.steps_done == 2
    assert done.summary.cards_reviewed == 2
    # The cards were rescheduled by the same FSRS path /review uses.
    activity = await routes.get_next_activity(user, db)
    assert activity.due_count == 0


# ── one engine, one student model ─────────────────────────────────────────


async def _lesson_with_quiz(
    db: AsyncSession,
    owner: User,
    settings: Settings,
    provider: Scripted,
    *,
    focus: bool,
    session_id: uuid.UUID | None,
) -> uuid.UUID:
    """Two turns of the same lesson: an opening, then a right quiz answer."""
    first = await _turn(
        db,
        owner,
        settings,
        provider,
        "Me ensine Freud.",
        session_id=session_id,
        focus=focus,
    )
    lesson_id = uuid.UUID(next(d for n, d in first if n == "session")["id"])
    reply = (
        (
            await db.execute(
                select(TeachingTurn)
                .where(TeachingTurn.session_id == lesson_id)
                .order_by(TeachingTurn.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    assert reply is not None
    reply.blocks = [QUIZ]
    await db.flush()
    await _turn(
        db,
        owner,
        settings,
        provider,
        "Guardado",
        session_id=lesson_id,
        focus=focus,
        event=LearningEventIn(
            kind="quiz",
            concept="inconsciente",
            correct=True,
            question="Onde?",
            chosen="Guardado",
        ),
    )
    return lesson_id


async def _knowledge(db: AsyncSession, owner: User) -> dict[str, Any]:
    journey = await db.scalar(
        select(LearningJourney).where(LearningJourney.owner_id == owner.id)
    )
    assert journey is not None
    states = (
        await db.execute(
            select(StudentConceptState)
            .where(StudentConceptState.journey_id == journey.id)
            .order_by(StudentConceptState.name)
        )
    ).scalars()
    events = (
        await db.execute(
            select(MasteryEvent)
            .where(MasteryEvent.journey_id == journey.id)
            .order_by(MasteryEvent.created_at)
        )
    ).scalars()
    progression = ProgressionEngine(db, owner.id, "UTC")
    await progression.sync()
    summary = await progression.summary()
    return {
        "states": [(s.name, s.state, s.evidence_count) for s in states],
        "events": [(e.kind, e.score) for e in events],
        "xp": summary.xp_total,
    }


async def test_a_focus_sitting_moves_the_same_student_model_as_a_normal_lesson(
    db: AsyncSession,
    user: User,
    other_user: User,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _mock_tiers(db)
    provider = Scripted()
    _patch(monkeypatch, provider)

    # Normal mode: an ordinary lesson.
    user.settings = {"learning_mode": "normal"}
    await _lesson_with_quiz(db, user, settings, provider, focus=False, session_id=None)
    normal_directive = provider.requests[-1].messages[-1].content
    assert "<FOCUS_MODE>" not in normal_directive

    # Modo TDAH: the preference still says "normal"; the sitting asks for focus.
    other_user.settings = {"learning_mode": "normal"}
    sitting = await routes.start_focus_session(
        FocusStartIn(minutes=5, goal="Me ensine Freud."), other_user, db
    )
    await _lesson_with_quiz(
        db,
        other_user,
        settings,
        provider,
        focus=True,
        session_id=sitting.teaching_session_id,
    )
    # The flag reached the engine: the focus layer and the small reply budget.
    focus_request = provider.requests[-1]
    assert "<FOCUS_MODE>" in focus_request.messages[-1].content
    assert "FOCUS DELIVERY" in focus_request.messages[0].content
    assert focus_request.max_tokens is not None and focus_request.max_tokens < 700

    step = await routes.focus_step(sitting.id, FocusStepIn(index=0), other_user, db)
    assert step.steps_done == 1

    normal = await _knowledge(db, user)
    focused = await _knowledge(db, other_user)
    assert normal["states"], "the lesson wrote no knowledge state"
    assert ("quiz", 1.0) in focused["events"]
    assert focused == normal

    # The sitting's summary reads the same rows.
    assert set(step.summary.concepts_touched) == {s[0] for s in focused["states"]}
    assert step.journey_id is not None
