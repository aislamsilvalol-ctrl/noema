"""Professor Noema orchestration: classification, tier resolution, dispatch.

`classify_intent` is tested with a scripted fake provider (no DB needed) — it
is pure decision logic once given a structured response. `tiered_gateway`/
`plan` are tested against the real, migration-seeded `ModelTierConfig` rows,
repointed at the "mock" provider (always constructible, no credentials
needed) the same way `test_db_pricing.py` repoints pricing rather than
inserting fresh ones under an already-used tier primary key. `professor_chat`
itself is tested the same way `chat()` is in `test_db_ai.py` — called
directly as a coroutine, its `StreamingResponse` body drained with the same
`collect_sse` helper.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from noema.api.v1.ai import professor_chat
from noema.api.v1.deps import build_provider
from noema.api.v1.schemas import ChatIn, ChatMessageIn
from noema.core.config import Settings
from noema.core.crypto import SecretBox
from noema.db.models import (
    Card,
    CardOrigin,
    Concept,
    ConceptMastery,
    ConceptStatus,
    Difficulty,
    ModelTier,
    ModelTierConfig,
    Notebook,
    Question,
    QuestionType,
    Source,
    SourceKind,
    SourceStatus,
    Subject,
    User,
    Workspace,
)
from noema.db.repository import OwnedRepository
from noema.ingestion.pipeline import ingest_source
from noema.ingestion.storage import LocalStorage
from noema.providers.base import (
    Capabilities,
    ChatRequest,
    ChatResponse,
    EmbedRequest,
    EmbedResponse,
    HealthReport,
    ProviderError,
    StreamEvent,
    StructuredRequest,
    TaskClass,
)
from noema.providers.gateway import AIGateway
from noema.providers.mock import MockProvider
from noema.services.professor import (
    Intent,
    classify_intent,
    needs_notebook_material,
    plan,
    tiered_gateway,
)

pytestmark = pytest.mark.asyncio


async def collect_sse(body: Any) -> list[tuple[str, dict[str, Any]]]:
    """Decode ``event: ...\\ndata: ...\\n\\n`` frames back into (event, payload)."""
    events: list[tuple[str, dict[str, Any]]] = []
    async for chunk in body:
        text = chunk.decode() if isinstance(chunk, bytes) else chunk
        lines = text.strip("\n").split("\n")
        name = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        events.append((name, data))
    return events


DOC = b"""# Cardiac Cycle

## Diastole

Diastole is the phase in which the ventricles fill with blood.

## Systole

Systole is the phase in which the ventricles contract and eject blood.
"""


class ScriptedStructuredProvider:
    """A fake whose `structured()` returns exactly the payload it's given."""

    name = "fake"
    capabilities = Capabilities(chat=True, structured_output="native")

    def __init__(self, payload: dict[str, Any] | Exception) -> None:
        self._payload = payload

    async def chat(self, request: ChatRequest) -> ChatResponse:
        raise NotImplementedError

    # The bare `yield` below is never reached -- it exists only so this method's
    # *syntax* makes it an async generator, matching `AIProvider.stream`'s
    # `AsyncIterator` return type. Every test using this fake exercises
    # `structured()`, never `stream()`.
    async def stream(self, request: ChatRequest) -> Any:
        raise NotImplementedError
        yield  # type: ignore[unreachable]

    async def embed(self, request: EmbedRequest) -> EmbedResponse:
        raise NotImplementedError

    async def structured(self, request: StructuredRequest) -> dict[str, Any]:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    async def health(self) -> HealthReport:
        raise NotImplementedError


@pytest.fixture
async def notebook(db: AsyncSession, user: User) -> Notebook:
    workspace = await OwnedRepository(db, Workspace, user.id).create(
        title="Bio", slug=f"bio-{uuid.uuid4().hex[:8]}"
    )
    subject = await OwnedRepository(db, Subject, user.id).create(
        workspace_id=workspace.id, title="Cells", slug=f"cells-{uuid.uuid4().hex[:8]}"
    )
    return await OwnedRepository(db, Notebook, user.id).create(
        subject_id=subject.id,
        title="Organelles",
        slug=f"org-{uuid.uuid4().hex[:8]}",
        retrieval_settings={},
    )


async def _ingest_material(
    db: AsyncSession, user: User, notebook: Notebook, settings: Settings, tmp_path: Path
) -> None:
    storage = LocalStorage(str(tmp_path))
    source = await OwnedRepository(db, Source, user.id).create(
        notebook_id=notebook.id,
        kind=SourceKind.MD,
        original_filename="cardiac.md",
        byte_size=len(DOC),
        status=SourceStatus.PENDING,
    )
    key = f"{user.id}/{source.id}.md"
    await storage.put(key, DOC)
    source.storage_key = key
    await db.flush()

    embed_gateway = AIGateway(MockProvider(dimensions=settings.noema_embedding_dim))
    await ingest_source(
        db, source.id, storage=storage, gateway=embed_gateway, settings=settings
    )


# ---------------------------------------------------------------------------
# classify_intent
# ---------------------------------------------------------------------------


async def test_classify_intent_returns_the_scripted_intent() -> None:
    gateway = AIGateway(ScriptedStructuredProvider({"intent": "quiz_me"}))

    intent = await classify_intent(gateway, "me testa em sístole", model=None)

    assert intent is Intent.QUIZ_ME


async def test_classify_intent_fails_safe_to_explain_on_a_provider_error() -> None:
    gateway = AIGateway(
        ScriptedStructuredProvider(ProviderError("down", provider="fake"))
    )

    intent = await classify_intent(gateway, "qualquer coisa", model=None)

    assert intent is Intent.EXPLAIN


async def test_classify_intent_fails_safe_to_explain_on_an_unknown_value() -> None:
    # A provider that doesn't honour the schema's enum constraint -- classify_intent
    # must not propagate a ValueError from Intent() into the chat response.
    gateway = AIGateway(ScriptedStructuredProvider({"intent": "make_me_a_sandwich"}))

    intent = await classify_intent(gateway, "qualquer coisa", model=None)

    assert intent is Intent.EXPLAIN


# ---------------------------------------------------------------------------
# tiered_gateway / plan
# ---------------------------------------------------------------------------


async def test_tiered_gateway_resolves_the_seeded_tiers_model(
    db: AsyncSession, settings: Settings
) -> None:
    economy = await db.get(ModelTierConfig, ModelTier.ECONOMY)
    assert economy is not None
    economy.provider = "mock"
    economy.model = "mock-economy-model"
    await db.flush()

    default_gateway = AIGateway(MockProvider())

    call = await tiered_gateway(
        ModelTier.ECONOMY,
        db=db,
        default_gateway=default_gateway,
        build_provider=build_provider,
        settings=settings,
        credentials=None,
    )

    assert call.model == "mock-economy-model"
    assert call.gateway is not default_gateway
    assert isinstance(call.gateway.primary, MockProvider)


async def test_tiered_gateway_falls_back_when_the_tiers_provider_is_unavailable(
    db: AsyncSession, settings: Settings
) -> None:
    standard = await db.get(ModelTierConfig, ModelTier.STANDARD)
    assert standard is not None
    standard.provider = "not-a-real-provider"
    await db.flush()

    default_gateway = AIGateway(MockProvider())

    call = await tiered_gateway(
        ModelTier.STANDARD,
        db=db,
        default_gateway=default_gateway,
        build_provider=build_provider,
        settings=settings,
        credentials=None,
    )

    assert call.model is None
    assert call.gateway is default_gateway


async def test_plan_escalates_deepen_to_the_premium_tiers_model(
    db: AsyncSession, settings: Settings
) -> None:
    premium = await db.get(ModelTierConfig, ModelTier.PREMIUM)
    assert premium is not None
    premium.provider = "mock"
    premium.model = "mock-premium-model"
    await db.flush()

    dispatch = await plan(
        Intent.DEEPEN,
        db=db,
        default_gateway=AIGateway(MockProvider()),
        build_provider=build_provider,
        settings=settings,
        credentials=None,
    )

    assert dispatch.task is TaskClass.TUTOR_CHAT
    assert dispatch.mode == "explain"
    assert dispatch.call.model == "mock-premium-model"


async def test_plan_routes_quiz_me_to_the_generate_questions_task_class(
    db: AsyncSession, settings: Settings
) -> None:
    dispatch = await plan(
        Intent.QUIZ_ME,
        db=db,
        default_gateway=AIGateway(MockProvider()),
        build_provider=build_provider,
        settings=settings,
        credentials=None,
    )

    assert dispatch.task is TaskClass.GENERATE_QUESTIONS


async def test_plan_routes_create_exam_to_the_economy_tier(
    db: AsyncSession, settings: Settings
) -> None:
    dispatch = await plan(
        Intent.CREATE_EXAM,
        db=db,
        default_gateway=AIGateway(MockProvider()),
        build_provider=build_provider,
        settings=settings,
        credentials=None,
    )

    economy = await db.get(ModelTierConfig, ModelTier.ECONOMY)
    assert economy is not None
    assert dispatch.call.model == economy.model


# ---------------------------------------------------------------------------
# needs_notebook_material
# ---------------------------------------------------------------------------


def test_quiz_me_needs_a_notebook() -> None:
    assert needs_notebook_material(Intent.QUIZ_ME, None) is True
    assert needs_notebook_material(Intent.QUIZ_ME, uuid.uuid4()) is False


def test_create_exam_needs_a_notebook() -> None:
    assert needs_notebook_material(Intent.CREATE_EXAM, None) is True
    assert needs_notebook_material(Intent.CREATE_EXAM, uuid.uuid4()) is False


def test_explain_never_needs_a_notebook() -> None:
    assert needs_notebook_material(Intent.EXPLAIN, None) is False


# ---------------------------------------------------------------------------
# professor_chat (route level)
# ---------------------------------------------------------------------------


async def test_professor_chat_dispatches_quiz_me_and_writes_real_questions(
    db: AsyncSession,
    user: User,
    notebook: Notebook,
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ingest_material(db, user, notebook, settings, tmp_path)

    # Both the economy classification call and the standard-tier dispatch call
    # need a real, working structured() -- point every tier at "mock" so this
    # test exercises the actual route rather than mocking the route itself.
    for tier in (ModelTier.ECONOMY, ModelTier.STANDARD):
        config = await db.get(ModelTierConfig, tier)
        assert config is not None
        config.provider = "mock"
        config.model = "mock-model"
    await db.flush()

    box = SecretBox.from_base64(settings.noema_master_key)

    payload = ChatIn(
        notebook_id=notebook.id,
        messages=[ChatMessageIn(role="user", content="me testa sobre sístole")],
        grounded=True,
    )

    class ForceQuizMeProvider(MockProvider):
        async def structured(self, request: StructuredRequest) -> dict[str, Any]:
            if request.task is TaskClass.CLASSIFY_INTENT:
                return {"intent": "quiz_me"}
            if request.task is TaskClass.GENERATE_QUESTIONS:
                # A real question payload, not MockProvider's generic schema
                # skeleton -- test_db_questions.py's own FakeProvider docstring
                # explains why: a skeleton produces identical/unparseable
                # content that generate_questions()'s own storage filters
                # correctly discard, so this would silently store zero
                # questions and the test would pass for the wrong reason.
                return {
                    "questions": [
                        {
                            "type": "mcq",
                            "difficulty": "medium",
                            "prompt": "What happens during systole?",
                            "concept": "systole",
                            "options": ["Ventricles contract", "Ventricles fill"],
                            "correct_index": 0,
                            "explanation": "",
                        }
                    ]
                }
            return await super().structured(request)

    provider = ForceQuizMeProvider(dimensions=settings.noema_embedding_dim)

    # tiered_gateway() re-resolves each tier through the real provider registry
    # (build_provider("mock", ...)) rather than reusing the gateway passed in
    # below -- that gateway is only the *default*, un-tiered fallback. Patch
    # the registry lookup itself so both the economy classification call and
    # the standard-tier dispatch call land on this one scripted instance,
    # instead of a fresh, un-scripted `MockProvider` neither test controls.
    async def fake_build_provider(
        name: str, settings_: Settings, credentials: Any
    ) -> MockProvider:
        return provider

    monkeypatch.setattr("noema.api.v1.deps.build_provider", fake_build_provider)

    response = await professor_chat(
        payload,
        user=user,
        db=db,
        gateway=AIGateway(provider),
        settings=settings,
        box=box,
    )

    events = await collect_sse(response.body_iterator)

    names = [name for name, _ in events]
    assert names == ["intent", "action", "done"]
    assert events[0][1]["intent"] == "quiz_me"
    action = events[1][1]
    assert action["intent"] == "quiz_me"
    assert action["count"] > 0


async def test_professor_chat_falls_back_to_explain_when_classification_fails(
    db: AsyncSession, user: User, settings: Settings
) -> None:
    # Deliberately doesn't repoint the economy tier's provider away from the
    # migration-seeded "anthropic" with no test API key configured -- that
    # itself exercises tiered_gateway()'s own fallback (an unbuildable
    # provider degrades to the injected gateway below), landing on this
    # scripted provider either way, whether the failure happens building the
    # tier's provider or calling structured() on it.
    box = SecretBox.from_base64(settings.noema_master_key)
    payload = ChatIn(
        notebook_id=None,
        messages=[ChatMessageIn(role="user", content="oi")],
        grounded=True,
    )

    class FailClassifyProvider(MockProvider):
        async def structured(self, request: StructuredRequest) -> dict[str, Any]:
            raise ProviderError("down", provider="fake")

    response = await professor_chat(
        payload,
        user=user,
        db=db,
        gateway=AIGateway(FailClassifyProvider()),
        settings=settings,
        box=box,
    )

    events = await collect_sse(response.body_iterator)

    assert events[0] == ("intent", {"intent": "explain"})
    assert events[-1][0] == "done"


# ---------------------------------------------------------------------------
# Memory integration (Phase 3)
# ---------------------------------------------------------------------------


async def test_explain_includes_the_student_memory_block(
    db: AsyncSession,
    user: User,
    notebook: Notebook,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Professor's own selective memory (build_memory) has its own
    dedicated, thorough tests in test_db_professor_memory.py -- this only
    proves the two are actually wired together: an EXPLAIN turn's outgoing
    request carries a rendered <STUDENT_MEMORY> block when the notebook has
    one to give it.
    """
    subject = await db.get(Subject, notebook.subject_id)
    assert subject is not None
    concept = Concept(
        owner_id=user.id,
        workspace_id=subject.workspace_id,
        name="Chain rule",
        normalized_name="chain rule",
        status=ConceptStatus.ACTIVE,
        difficulty_prior=0.5,
        aliases=[],
        source_chunk_ids=[],
    )
    db.add(concept)
    await db.flush()
    db.add(
        Card(
            owner_id=user.id,
            notebook_id=notebook.id,
            concept_id=concept.id,
            front_md="front",
            back_md="back",
            origin=CardOrigin.USER,
            source_chunk_ids=[],
        )
    )
    db.add(
        ConceptMastery(
            owner_id=user.id,
            concept_id=concept.id,
            mastery=0.4,
            evidence_count=2.0,
        )
    )
    await db.flush()

    for tier in (ModelTier.ECONOMY, ModelTier.STANDARD):
        config = await db.get(ModelTierConfig, tier)
        assert config is not None
        config.provider = "mock"
        config.model = "mock-model"
    await db.flush()

    box = SecretBox.from_base64(settings.noema_master_key)
    payload = ChatIn(
        notebook_id=notebook.id,
        messages=[ChatMessageIn(role="user", content="explica de novo")],
        grounded=False,
    )

    captured: list[ChatRequest] = []

    class ForceExplainProvider(MockProvider):
        async def structured(self, request: StructuredRequest) -> dict[str, Any]:
            return {"intent": "explain"}

        async def stream(self, request: ChatRequest) -> Any:
            captured.append(request)
            yield StreamEvent(done=True)

    provider = ForceExplainProvider()

    async def fake_build_provider(
        name: str, settings_: Settings, credentials: Any
    ) -> MockProvider:
        return provider

    monkeypatch.setattr("noema.api.v1.deps.build_provider", fake_build_provider)

    response = await professor_chat(
        payload,
        user=user,
        db=db,
        gateway=AIGateway(provider),
        settings=settings,
        box=box,
    )
    await collect_sse(response.body_iterator)

    assert len(captured) == 1
    memory_messages = [m for m in captured[0].messages if "<STUDENT_MEMORY>" in m.content]
    assert len(memory_messages) == 1
    assert "Chain rule: 40% mastery" in memory_messages[0].content


async def test_summarize_never_includes_the_student_memory_block(
    db: AsyncSession,
    user: User,
    notebook: Notebook,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SUMMARIZE condenses what's already in front of it -- it should never
    pull in mastery/misconception context, even when the notebook has some.
    """
    subject = await db.get(Subject, notebook.subject_id)
    assert subject is not None
    concept = Concept(
        owner_id=user.id,
        workspace_id=subject.workspace_id,
        name="Chain rule",
        normalized_name="chain rule",
        status=ConceptStatus.ACTIVE,
        difficulty_prior=0.5,
        aliases=[],
        source_chunk_ids=[],
    )
    db.add(concept)
    await db.flush()
    db.add(
        Card(
            owner_id=user.id,
            notebook_id=notebook.id,
            concept_id=concept.id,
            front_md="front",
            back_md="back",
            origin=CardOrigin.USER,
            source_chunk_ids=[],
        )
    )
    db.add(ConceptMastery(owner_id=user.id, concept_id=concept.id, mastery=0.4))
    await db.flush()

    for tier in (ModelTier.ECONOMY, ModelTier.STANDARD):
        config = await db.get(ModelTierConfig, tier)
        assert config is not None
        config.provider = "mock"
        config.model = "mock-model"
    await db.flush()

    box = SecretBox.from_base64(settings.noema_master_key)
    payload = ChatIn(
        notebook_id=notebook.id,
        messages=[ChatMessageIn(role="user", content="resume isso")],
        grounded=False,
    )

    captured: list[ChatRequest] = []

    class ForceSummarizeProvider(MockProvider):
        async def structured(self, request: StructuredRequest) -> dict[str, Any]:
            return {"intent": "summarize"}

        async def stream(self, request: ChatRequest) -> Any:
            captured.append(request)
            yield StreamEvent(done=True)

    provider = ForceSummarizeProvider()

    async def fake_build_provider(
        name: str, settings_: Settings, credentials: Any
    ) -> MockProvider:
        return provider

    monkeypatch.setattr("noema.api.v1.deps.build_provider", fake_build_provider)

    response = await professor_chat(
        payload,
        user=user,
        db=db,
        gateway=AIGateway(provider),
        settings=settings,
        box=box,
    )
    await collect_sse(response.body_iterator)

    assert len(captured) == 1
    assert not any("<STUDENT_MEMORY>" in m.content for m in captured[0].messages)


# ---------------------------------------------------------------------------
# CREATE_EXAM dispatch
# ---------------------------------------------------------------------------


async def test_professor_chat_dispatches_create_exam_and_starts_a_real_exam(
    db: AsyncSession,
    user: User,
    notebook: Notebook,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for i in range(3):
        await OwnedRepository(db, Question, user.id).create(
            notebook_id=notebook.id,
            concept_id=None,
            type=QuestionType.TRUE_FALSE,
            difficulty=Difficulty.MEDIUM,
            prompt=f"Statement {i}",
            payload={"answer": True, "explanation": "because"},
        )

    box = SecretBox.from_base64(settings.noema_master_key)
    payload = ChatIn(
        notebook_id=notebook.id,
        messages=[ChatMessageIn(role="user", content="quero fazer uma prova")],
        grounded=False,
    )

    class ForceCreateExamProvider(MockProvider):
        async def structured(self, request: StructuredRequest) -> dict[str, Any]:
            return {"intent": "create_exam"}

    provider = ForceCreateExamProvider()

    async def fake_build_provider(
        name: str, settings_: Settings, credentials: Any
    ) -> MockProvider:
        return provider

    monkeypatch.setattr("noema.api.v1.deps.build_provider", fake_build_provider)

    response = await professor_chat(
        payload,
        user=user,
        db=db,
        gateway=AIGateway(provider),
        settings=settings,
        box=box,
    )

    events = await collect_sse(response.body_iterator)

    names = [name for name, _ in events]
    assert names == ["intent", "action", "done"]
    assert events[0][1]["intent"] == "create_exam"
    action = events[1][1]
    assert action["intent"] == "create_exam"
    assert action["minutes"] == 20
    exam_id = uuid.UUID(action["exam_id"])

    from noema.db.models import Exam

    exam = await OwnedRepository(db, Exam, user.id).get(exam_id)
    assert exam.notebook_id == notebook.id
    assert exam.submitted_at is None


async def test_professor_chat_create_exam_reports_a_friendly_error_with_no_questions(
    db: AsyncSession,
    user: User,
    notebook: Notebook,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The notebook has no generated questions yet -- `start_exam` refuses.

    That refusal has to reach the client as an `error` SSE frame, not an
    unhandled exception blowing up an already-accepted stream.
    """
    box = SecretBox.from_base64(settings.noema_master_key)
    payload = ChatIn(
        notebook_id=notebook.id,
        messages=[ChatMessageIn(role="user", content="cria uma prova pra mim")],
        grounded=False,
    )

    class ForceCreateExamProvider(MockProvider):
        async def structured(self, request: StructuredRequest) -> dict[str, Any]:
            return {"intent": "create_exam"}

    provider = ForceCreateExamProvider()

    async def fake_build_provider(
        name: str, settings_: Settings, credentials: Any
    ) -> MockProvider:
        return provider

    monkeypatch.setattr("noema.api.v1.deps.build_provider", fake_build_provider)

    response = await professor_chat(
        payload,
        user=user,
        db=db,
        gateway=AIGateway(provider),
        settings=settings,
        box=box,
    )

    events = await collect_sse(response.body_iterator)

    names = [name for name, _ in events]
    assert names == ["intent", "error"]
    assert "questions" in events[1][1]["message"].lower()
