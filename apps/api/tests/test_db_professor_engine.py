"""`POST /ai/professor` as the V3 Professor Engine: journeys, moves, blocks as
events, the student model, cards, compaction, assessments.

Called directly as a coroutine, its `StreamingResponse` drained with
`collect_sse`, against the real, migration-seeded database — the same way the
V2 route was tested. Every model call is the mock provider or a scripted one;
nothing here spends a token.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.api.v1.ai import professor_chat
from noema.api.v1.schemas import ChatIn, ChatMessageIn, LearningEventIn
from noema.core.config import Settings
from noema.core.crypto import SecretBox
from noema.db.models import (
    AIUsage,
    Assessment,
    Card,
    LearningJourney,
    MasteryEvent,
    MemorySummary,
    ModelTier,
    ModelTierConfig,
    StudentConceptState,
    TeachingSession,
    TeachingTurn,
    User,
)
from noema.professor import assessment as assessments
from noema.professor import flashcards
from noema.professor.student import StudentModel
from noema.providers.base import ChatRequest, StreamEvent, StructuredRequest, Usage
from noema.providers.gateway import AIGateway
from noema.providers.mock import MockProvider
from noema.services.teaching_session import TeachingSessions
from noema.services.usage import UsageWriter

pytestmark = pytest.mark.asyncio


async def collect_sse(body: Any) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    async for chunk in body:
        text = chunk.decode() if isinstance(chunk, bytes) else chunk
        for frame in text.strip("\n").split("\n\n"):
            lines = frame.split("\n")
            name = lines[0].removeprefix("event: ")
            data = json.loads(lines[1].removeprefix("data: "))
            events.append((name, data))
    return events


PLAN = {
    "modules": [
        {
            "title": "Fundamentos",
            "lessons": [
                {"title": "O inconsciente", "concepts": ["inconsciente", "lapso"]},
                {"title": "Recalque", "concepts": ["recalque", "resistência"]},
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
MEMORY = {
    "goal": "Freud",
    "concepts_covered": ["inconsciente", "lapso"],
    "mastered": ["lapso"],
    "uncertain": [],
    "misconceptions": ["tudo que esqueci está no inconsciente"],
    "examples_that_worked": ["o lapso de língua"],
    "questions_answered": 1,
    "assessment_results": [],
    "learner_patterns": ["analogias funcionam"],
    "last_taught": "o inconsciente",
    "next_step": "recalque",
}
CARDS = {
    "cards": [
        {"front": "O que é um lapso, para Freud?", "back": "Um desejo que escapa."},
        {"front": "Consciente vs inconsciente?", "back": "O que vejo vs o que age."},
    ]
}
PAPER = {
    "title": "Checkpoint 1",
    "questions": [
        {
            "type": "mcq",
            "prompt": "O lapso mostra…",
            "concept": "lapso",
            "options": ["cansaço", "um desejo"],
            "correct_index": 1,
            "explanation": "porque",
        },
        {
            "type": "true_false",
            "prompt": "Tudo esquecido é recalcado.",
            "concept": "recalque",
            "answer": False,
        },
    ],
}


class Scripted(MockProvider):
    """Structured calls answer by task; the stream is a fixed reply."""

    def __init__(self, reply: str = "Olha isso. O que sobra embaixo da água?") -> None:
        super().__init__()
        self.reply = reply
        self.requests: list[ChatRequest] = []
        self.structured_requests: list[StructuredRequest] = []

    async def structured(self, request: StructuredRequest) -> dict[str, Any]:
        self.structured_requests.append(request)
        feature = request.metadata.get("feature", "")
        if feature == "professor.parse_goal":
            return GOAL
        if feature == "professor.curriculum":
            return PLAN
        if feature == "professor.route":
            return {"signal": "neutral"}
        if feature == "professor.compact":
            return MEMORY
        if feature == "professor.flashcards":
            return CARDS
        if feature == "professor.assessment":
            return PAPER
        return await super().structured(request)

    async def stream(self, request: ChatRequest) -> Any:
        self.requests.append(request)
        for word in self.reply.split(" "):
            yield StreamEvent(delta=word + " ")
        # A provider that reports its cache, the way Anthropic does.
        yield StreamEvent(
            done=True,
            usage=Usage(prompt_tokens=1200, completion_tokens=80, cached_tokens=900),
        )


async def _point_tiers_at_mock(db: AsyncSession) -> None:
    for tier in ModelTier:
        config = await db.get(ModelTierConfig, tier)
        assert config is not None
        config.provider = "mock"
        config.model = "mock-model"
    await db.flush()


def _patch_provider(monkeypatch: pytest.MonkeyPatch, provider: MockProvider) -> None:
    async def fake_build_provider(
        name: str, settings_: Settings, credentials: Any
    ) -> Any:
        return provider

    monkeypatch.setattr("noema.api.v1.deps.build_provider", fake_build_provider)


async def _turn(
    db: AsyncSession,
    user: User,
    settings: Settings,
    provider: MockProvider,
    text: str,
    *,
    session_id: uuid.UUID | None = None,
    event: LearningEventIn | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    response = await professor_chat(
        ChatIn(
            notebook_id=None,
            session_id=session_id,
            messages=[ChatMessageIn(role="user", content=text)],
            grounded=False,
            learning_event=event,
        ),
        user=user,
        db=db,
        gateway=AIGateway(provider, record_usage=UsageWriter(db, user.id)),
        settings=settings,
        box=SecretBox.from_base64(settings.noema_master_key),
    )
    return await collect_sse(response.body_iterator)


def _session_id(events: list[tuple[str, dict[str, Any]]]) -> uuid.UUID:
    return uuid.UUID(next(d for n, d in events if n == "session")["id"])


# ── the first turn ─────────────────────────────────────────────────────────


async def test_a_first_message_starts_a_journey_with_a_goal_and_a_plan(
    db: AsyncSession, user: User, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _point_tiers_at_mock(db)
    provider = Scripted()
    _patch_provider(monkeypatch, provider)

    events = await _turn(
        db, user, settings, provider, "Quero aprender psicologia segundo Freud do zero."
    )
    names = [n for n, _ in events]
    assert names[:5] == ["session", "journey", "move", "intent", "mino"]
    assert "done" in names

    journey_event = next(d for n, d in events if n == "journey")
    assert journey_event["subject"] == "Psicanálise freudiana"
    assert journey_event["plan"][0]["lessons"][0]["title"] == "O inconsciente"
    assert journey_event["current"]["concept"] == "inconsciente"

    move = next(d for n, d in events if n == "move")
    assert move["move"] == "teach"
    assert next(d for n, d in events if n == "mino")["state"] == "teaching"

    journey = await db.scalar(
        select(LearningJourney).where(LearningJourney.owner_id == user.id)
    )
    assert journey is not None
    assert journey.inferred_level == "introductory"
    assert journey.profile == {"language": "pt"}

    # Two structured calls before the first token: the goal and the plan.
    features = [r.metadata.get("feature") for r in provider.structured_requests]
    assert features == ["professor.parse_goal", "professor.curriculum"]

    # The teaching call: a stable system block, the learner's message, one
    # directive with the move layer and the course — no PEDAGOGY in tokens.
    request = provider.requests[0]
    assert "You are Mino" in request.messages[0].content
    assert "THIS TURN: TEACH" in request.messages[-1].content
    assert "<COURSE>" in request.messages[-1].content
    assert request.metadata["feature"] == "professor.teach"
    tokens = "".join(d["text"] for n, d in events if n == "token")
    assert "Olha isso." in tokens

    done = next(d for n, d in events if n == "done")
    assert done["context"]["transcript_turns"] == 1
    assert done["move"] == "teach"


async def test_the_second_turn_uses_the_stored_transcript_not_the_clients(
    db: AsyncSession, user: User, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _point_tiers_at_mock(db)
    provider = Scripted()
    _patch_provider(monkeypatch, provider)

    first = await _turn(db, user, settings, provider, "Me ensine Freud.")
    session_id = _session_id(first)
    await _turn(
        db, user, settings, provider, "E o que é o inconsciente?", session_id=session_id
    )

    request = provider.requests[-1]
    roles = [m.role.value for m in request.messages]
    # system, learner, Mino, learner, directive
    assert roles == ["system", "user", "assistant", "user", "user"]
    assert request.messages[2].content.startswith("Olha isso.")
    assert request.messages[3].content == "E o que é o inconsciente?"


# ── blocks and the pedagogy record ─────────────────────────────────────────

RECORD = (
    '{"subject": "Freud", "current_topic": "aparelho psíquico", '
    '"current_concept": "inconsciente", "learner_level": "introductory", '
    '"strategy": "analogy", "situation": "first_contact", "next_action": "check", '
    '"mastery_evidence": {"concept": "lapso", "verdict": "understood", '
    '"strength": "moderate"}, "plan": [{"topic": "inconsciente", "status": "current"}]}'
)


async def test_a_quiz_block_becomes_an_event_and_the_record_moves_the_lesson(
    db: AsyncSession, user: User, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _point_tiers_at_mock(db)
    reply = (
        "Pensa no lapso.\n\n```noema:quiz\n"
        '{"question": "Onde estava o nome?", "options": ["Sumiu", "Guardado"], '
        '"answer": 1, "explain": "Pré-consciente.", "concept": "inconsciente"}\n```\n'
        "Escolhe uma.\n<PEDAGOGY>" + RECORD + "</PEDAGOGY>"
    )
    provider = Scripted(reply)
    _patch_provider(monkeypatch, provider)

    events = await _turn(db, user, settings, provider, "Me ensine Freud.")
    tokens = "".join(d["text"] for n, d in events if n == "token")
    assert "noema:quiz" not in tokens and "PEDAGOGY" not in tokens
    assert "Pensa no lapso." in tokens and "Escolhe uma." in tokens

    block = next(d for n, d in events if n == "block")
    assert block["tool"] == "quiz"
    assert block["data"]["answer"] == 1
    assert ("mino", {"state": "questioning"}) in events

    session_id = _session_id(events)
    session = await TeachingSessions(db, user.id).sessions.get(session_id)
    await db.refresh(session)
    assert session.last_move == "question"
    turns = await TeachingSessions(db, user.id).history(session)
    assert turns[-1].blocks is not None and turns[-1].blocks[0]["tool"] == "quiz"
    assert turns[-1].token_estimate > 0

    journey = await db.get(LearningJourney, session.journey_id)
    assert journey is not None
    await db.refresh(journey)
    assert journey.current_concept == "inconsciente"
    states = {
        s.name: s
        for s in (
            await db.execute(
                select(StudentConceptState).where(
                    StudentConceptState.journey_id == journey.id
                )
            )
        ).scalars()
    }
    assert states["inconsciente"].state == "introduced"
    assert states["lapso"].evidence_count == 1
    assert states["lapso"].state == "learning"
    event = await db.scalar(
        select(MasteryEvent).where(MasteryEvent.journey_id == journey.id)
    )
    assert event is not None and event.kind == "conversation" and event.score == 1.0

    # Cards for the concept that landed with moderate evidence.
    cards = (
        (await db.execute(select(Card).where(Card.journey_id == journey.id)))
        .scalars()
        .all()
    )
    assert len(cards) == 2
    assert all(c.notebook_id is None and c.approved_at is None for c in cards)
    assert ("flashcards", next(d for n, d in events if n == "flashcards")) in events
    assert next(d for n, d in events if n == "mastery")["concept"] == "lapso"


async def test_a_quiz_answer_is_counted_and_routes_the_next_turn(
    db: AsyncSession, user: User, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _point_tiers_at_mock(db)
    provider = Scripted()
    _patch_provider(monkeypatch, provider)
    first = await _turn(db, user, settings, provider, "Me ensine Freud.")
    session_id = _session_id(first)

    wrong = await _turn(
        db,
        user,
        settings,
        provider,
        "Sumiu",
        session_id=session_id,
        event=LearningEventIn(
            kind="quiz",
            concept="inconsciente",
            correct=False,
            question="Onde?",
            chosen="Sumiu",
        ),
    )
    move = next(d for n, d in wrong if n == "move")
    assert move["move"] == "correct"
    assert move["strategy"] == "analogy"
    assert "THIS TURN: CORRECT" in provider.requests[-1].messages[-1].content

    right = await _turn(
        db,
        user,
        settings,
        provider,
        "Guardado",
        session_id=session_id,
        event=LearningEventIn(kind="quiz", concept="inconsciente", correct=True),
    )
    assert next(d for n, d in right if n == "move")["move"] == "advance"

    journey = (await db.execute(select(LearningJourney))).scalars().first()
    assert journey is not None
    kinds = [
        e.kind
        for e in (
            await db.execute(
                select(MasteryEvent)
                .where(MasteryEvent.journey_id == journey.id)
                .order_by(MasteryEvent.created_at)
            )
        ).scalars()
    ]
    assert kinds == ["quiz", "quiz"]


async def test_confusion_and_knowing_are_read_without_a_model(
    db: AsyncSession, user: User, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _point_tiers_at_mock(db)
    provider = Scripted()
    _patch_provider(monkeypatch, provider)
    first = await _turn(db, user, settings, provider, "Me ensine Freud.")
    session_id = _session_id(first)
    before = len(provider.structured_requests)

    lost = await _turn(
        db, user, settings, provider, "Não entendi.", session_id=session_id
    )
    assert next(d for n, d in lost if n == "move")["move"] == "correct"
    knows = await _turn(
        db, user, settings, provider, "Isso eu já sei.", session_id=session_id
    )
    assert next(d for n, d in knows if n == "move")["move"] == "advance"
    # No routing call was spent on either.
    assert len(provider.structured_requests) == before

    journey = (await db.execute(select(LearningJourney))).scalars().first()
    assert journey is not None
    await db.refresh(journey)
    # "Já sei" skipped the first lesson.
    assert journey.plan["modules"][0]["lessons"][0]["status"] == "skipped"
    assert journey.current_lesson == 1
    assert journey.current_concept == "recalque"


# ── memory ─────────────────────────────────────────────────────────────────


async def test_a_long_lesson_is_compacted_and_the_context_stays_bounded(
    db: AsyncSession, user: User, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _point_tiers_at_mock(db)
    monkeypatch.setattr(settings, "noema_professor_compact_after_turns", 8)
    monkeypatch.setattr(settings, "noema_professor_keep_turns", 4)
    provider = Scripted("Uma resposta razoavelmente longa sobre o inconsciente. " * 6)
    _patch_provider(monkeypatch, provider)

    first = await _turn(db, user, settings, provider, "Me ensine Freud.")
    session_id = _session_id(first)
    compacted_at: int | None = None
    for i in range(6):
        events = await _turn(
            db,
            user,
            settings,
            provider,
            f"Pergunta {i} sobre o inconsciente",
            session_id=session_id,
        )
        if any(n == "memory" for n, _ in events) and compacted_at is None:
            compacted_at = i
    assert compacted_at is not None

    summary = await db.scalar(
        select(MemorySummary).where(MemorySummary.owner_id == user.id)
    )
    assert summary is not None
    assert summary.summary["mastered"] == ["lapso"]
    assert summary.tokens_saved > 0
    archived = (
        (
            await db.execute(
                select(TeachingTurn).where(
                    TeachingTurn.session_id == session_id,
                    TeachingTurn.archived_at.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    assert archived  # kept, not deleted

    # The next request carries the memory block and only the kept turns.
    request = provider.requests[-1]
    # After a compaction the directive carries the hand-off form.
    assert "<CONTEXT>" in request.messages[-1].content
    assert "Earlier in this lesson" in request.messages[-1].content
    assert "WHO:" in request.messages[-1].content
    chat_turns = list(request.messages[1:-1])
    assert len(chat_turns) <= 5

    # L2/L3: the summary reached the student model and the profile.
    journey = (await db.execute(select(LearningJourney))).scalars().first()
    assert journey is not None
    await db.refresh(journey)
    assert journey.profile["patterns"] == ["analogias funcionam"]
    state = await StudentModel(db, user.id, journey).get("inconsciente")
    assert state is not None
    assert "tudo que esqueci está no inconsciente" in state.misconceptions


# ── cards and assessments outside the stream ───────────────────────────────


async def test_recalling_a_lesson_card_approves_it_and_counts(
    db: AsyncSession, user: User, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _point_tiers_at_mock(db)
    provider = Scripted("Pronto.\n<PEDAGOGY>" + RECORD + "</PEDAGOGY>")
    _patch_provider(monkeypatch, provider)
    await _turn(db, user, settings, provider, "Me ensine Freud.")
    journey = (await db.execute(select(LearningJourney))).scalars().first()
    assert journey is not None
    card = (
        (await db.execute(select(Card).where(Card.journey_id == journey.id)))
        .scalars()
        .first()
    )
    assert card is not None
    approved_before = card.approved_at
    assert approved_before is None

    outcome = await flashcards.recall(
        db, owner_id=user.id, journey=journey, card_id=card.id, rating=3
    )
    await db.refresh(card)
    assert card.approved_at is not None
    assert outcome["concept"] == "lapso"
    events = (
        (
            await db.execute(
                select(MasteryEvent).where(MasteryEvent.concept_name == "lapso")
            )
        )
        .scalars()
        .all()
    )
    assert [e.kind for e in events] == ["conversation", "flashcard"]


async def test_a_checkpoint_writes_a_paper_and_grading_feeds_the_next_turn(
    db: AsyncSession, user: User, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _point_tiers_at_mock(db)
    monkeypatch.setattr(settings, "noema_professor_checkpoint_every_concepts", 2)
    provider = Scripted("Pronto.\n<PEDAGOGY>" + RECORD + "</PEDAGOGY>")
    _patch_provider(monkeypatch, provider)

    first = await _turn(db, user, settings, provider, "Me ensine Freud.")
    session_id = _session_id(first)
    # Two concepts introduced (inconsciente, lapso), at a boundary: an exam.
    second = await _turn(db, user, settings, provider, "Continua.", session_id=session_id)
    assert next(d for n, d in second if n == "move")["move"] == "exam"
    checkpoint = next(d for n, d in second if n == "checkpoint")
    assert checkpoint["kind"] == "checkpoint"
    assert "correct_index" not in json.dumps(checkpoint)
    assert "THIS TURN: CHECKPOINT" in provider.requests[-1].messages[-1].content

    journey = (await db.execute(select(LearningJourney))).scalars().first()
    assert journey is not None
    paper = await db.get(Assessment, uuid.UUID(checkpoint["id"]))
    assert paper is not None and paper.status == "open"

    graded = await assessments.submit(
        db,
        owner_id=user.id,
        journey=journey,
        assessment_id=paper.id,
        responses=[1, True],
        gateway=None,
        model=None,
    )
    assert graded.score == 0.5
    assert graded.results["weak"] == ["recalque"]
    await db.refresh(journey)
    assert journey.pending_remediation == ["recalque"]

    third = await _turn(
        db,
        user,
        settings,
        provider,
        "Terminei.",
        session_id=session_id,
        event=LearningEventIn(kind="assessment", assessment_id=paper.id),
    )
    move = next(d for n, d in third if n == "move")
    assert move["move"] == "correct"
    directive = provider.requests[-1].messages[-1].content
    assert "Correct these first: recalque" in directive
    assert "<ASSESSMENT_RESULTS>" in directive


# ── accounting and tenancy ─────────────────────────────────────────────────


async def test_every_call_is_recorded_with_its_feature_and_session(
    db: AsyncSession, user: User, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _point_tiers_at_mock(db)
    provider = Scripted()
    _patch_provider(monkeypatch, provider)
    events = await _turn(db, user, settings, provider, "Me ensine Freud.")
    session_id = _session_id(events)
    rows = (
        (await db.execute(select(AIUsage).where(AIUsage.owner_id == user.id)))
        .scalars()
        .all()
    )
    features = sorted(r.feature or "" for r in rows)
    assert "professor.teach" in features
    assert "professor.parse_goal" in features and "professor.curriculum" in features
    teach = next(r for r in rows if r.feature == "professor.teach")
    assert teach.session_id == session_id
    assert teach.cached_tokens == 900 and teach.prompt_tokens == 1200


async def test_another_users_journey_is_nobodys_business(
    db: AsyncSession, user: User, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from noema.core.errors import NotFound
    from noema.db.repository import OwnedRepository
    from noema.services.auth import AuthService

    await _point_tiers_at_mock(db)
    provider = Scripted()
    _patch_provider(monkeypatch, provider)
    await _turn(db, user, settings, provider, "Me ensine Freud.")
    journey = (await db.execute(select(LearningJourney))).scalars().first()
    assert journey is not None

    other = await AuthService(db, settings).register(
        f"other-{uuid.uuid4().hex[:8]}@example.com", "a-long-enough-password", "Other"
    )
    with pytest.raises(NotFound):
        await OwnedRepository(db, LearningJourney, other.id).get(journey.id)
    session = await db.scalar(
        select(TeachingSession).where(TeachingSession.owner_id == user.id)
    )
    assert session is not None and session.journey_id == journey.id
