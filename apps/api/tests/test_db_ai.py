"""The AI endpoints: streaming tutor chat, provider inventory, BYOK credentials.

`chat()` is tested by calling it directly and draining its `StreamingResponse`'s
body iterator — the same "call the route function as a plain coroutine" convention
the rest of this suite uses for `noema.api.v1.study`, extended here to a streaming
endpoint. `_assemble` and `_sse` are pure and tested with no DB at all.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from noema.api.v1.ai import _assemble, _sse, chat, list_providers
from noema.api.v1.schemas import ChatIn, ChatMessageIn
from noema.core.config import Settings
from noema.core.crypto import SecretBox
from noema.core.errors import NotFound
from noema.db.models import (
    Notebook,
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
)
from noema.providers.gateway import AIGateway
from noema.providers.mock import MockProvider
from noema.retrieval.search import Retrieved
from noema.services.credentials import CredentialService

pytestmark = pytest.mark.asyncio

DOC = b"""# Cardiac Cycle

## Diastole

Diastole is the phase in which the ventricles fill with blood.

## Systole

Systole is the phase in which the ventricles contract and eject blood.
"""


class StreamingFakeProvider:
    """A scripted ``AIProvider`` whose ``stream()`` yields exactly what's given."""

    name = "fake"
    capabilities = Capabilities(chat=True, streaming=True)

    def __init__(self, events: list[StreamEvent] | Exception) -> None:
        self._events = events

    async def chat(self, request: ChatRequest) -> ChatResponse:
        raise NotImplementedError

    async def stream(self, request: ChatRequest) -> Any:
        if isinstance(self._events, Exception):
            raise self._events
        for event in self._events:
            yield event

    async def embed(self, request: EmbedRequest) -> EmbedResponse:
        raise NotImplementedError

    async def structured(self, request: StructuredRequest) -> dict[str, Any]:
        raise NotImplementedError

    async def health(self) -> HealthReport:
        raise NotImplementedError


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


def chat_in(*, notebook_id: uuid.UUID | None = None, grounded: bool = True) -> ChatIn:
    return ChatIn(
        notebook_id=notebook_id,
        messages=[ChatMessageIn(role="user", content="What fills the ventricles?")],
        grounded=grounded,
    )


# ---------------------------------------------------------------------------
# _assemble / _sse (pure)
# ---------------------------------------------------------------------------


def a_result() -> Retrieved:
    return Retrieved(
        chunk_id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        content="Diastole fills the ventricles.",
        heading_path=["Cardiac Cycle", "Diastole"],
        page_from=1,
        page_to=1,
        source_title="Physiology 101",
        score=0.9,
        found_by_both=True,
    )


def test_assemble_ungrounded_uses_the_plain_tutor_prompt() -> None:
    _, context, cited = _assemble("explain", False, [a_result()])

    assert context == ""
    assert cited == []


def test_assemble_grounded_with_no_results_uses_the_no_context_prompt() -> None:
    _, context, cited = _assemble("explain", True, [])

    assert context == ""
    assert cited == []


def test_assemble_grounded_with_results_builds_context_and_keeps_citations() -> None:
    _, context, cited = _assemble("explain", True, [a_result()])

    assert "Diastole fills the ventricles." in context
    assert len(cited) == 1


def test_sse_formats_a_named_event_with_json_data() -> None:
    frame = _sse("token", {"text": "hi"})

    assert frame == b'event: token\ndata: {"text": "hi"}\n\n'


# ---------------------------------------------------------------------------
# chat
# ---------------------------------------------------------------------------


async def test_chat_raises_not_found_for_another_owners_notebook(
    db: AsyncSession,
    user: User,
    other_user: User,
    notebook: Notebook,
    settings: Settings,
) -> None:
    gateway = AIGateway(MockProvider())
    with pytest.raises(NotFound):
        await chat(
            chat_in(notebook_id=notebook.id),
            user=other_user,
            db=db,
            gateway=gateway,
            settings=settings,
        )


async def test_chat_ungrounded_streams_tokens_and_ends_with_done(
    db: AsyncSession, user: User, settings: Settings
) -> None:
    gateway = AIGateway(MockProvider())

    response = await chat(
        chat_in(notebook_id=None), user=user, db=db, gateway=gateway, settings=settings
    )
    events = await collect_sse(response.body_iterator)

    names = [name for name, _ in events]
    assert "sources" not in names
    assert "token" in names
    assert names[-1] == "done"
    done = dict(events[-1][1])
    assert done["grounded"] is False


async def test_chat_grounded_with_no_material_gets_no_sources_event(
    db: AsyncSession, user: User, notebook: Notebook, settings: Settings
) -> None:
    gateway = AIGateway(MockProvider())

    response = await chat(
        chat_in(notebook_id=notebook.id),
        user=user,
        db=db,
        gateway=gateway,
        settings=settings,
    )
    events = await collect_sse(response.body_iterator)

    names = [name for name, _ in events]
    assert "sources" not in names
    done = dict(events[-1][1])
    assert done["grounded"] is True


async def test_chat_streams_an_error_event_on_a_mid_stream_provider_error(
    db: AsyncSession, user: User, settings: Settings
) -> None:
    gateway = AIGateway(
        StreamingFakeProvider(ProviderError("down", provider="fake", retryable=False))
    )

    response = await chat(
        chat_in(notebook_id=None), user=user, db=db, gateway=gateway, settings=settings
    )
    events = await collect_sse(response.body_iterator)

    assert events[-1][0] == "error"
    assert events[-1][1]["provider"] == "fake"


async def test_chat_grounded_with_real_material_sends_a_sources_event(
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

    payload = ChatIn(
        notebook_id=notebook.id,
        messages=[ChatMessageIn(role="user", content="Diastole fills the ventricles")],
        grounded=True,
    )
    response = await chat(
        payload,
        user=user,
        db=db,
        gateway=AIGateway(MockProvider(dimensions=settings.noema_embedding_dim)),
        settings=settings,
    )
    events = await collect_sse(response.body_iterator)

    names = [name for name, _ in events]
    assert "sources" in names
    sources = dict(next(data for name, data in events if name == "sources"))
    assert len(sources["citations"]) > 0
    done = dict(events[-1][1])
    assert done["grounded"] is True


# ---------------------------------------------------------------------------
# list_providers
# ---------------------------------------------------------------------------


async def test_mock_and_ollama_are_always_configured(
    db: AsyncSession, user: User, settings: Settings
) -> None:
    box = SecretBox.from_base64(settings.noema_master_key)

    providers = await list_providers(user=user, db=db, settings=settings, box=box)

    by_name = {p.name: p for p in providers}
    assert by_name["mock"].configured is True
    assert by_name["ollama"].configured is True


async def test_a_provider_with_no_key_anywhere_is_not_configured(
    db: AsyncSession, user: User, settings: Settings
) -> None:
    box = SecretBox.from_base64(settings.noema_master_key)

    providers = await list_providers(user=user, db=db, settings=settings, box=box)

    by_name = {p.name: p for p in providers}
    assert by_name["anthropic"].configured is False
    assert by_name["anthropic"].capabilities == {}


async def test_a_stored_byok_key_is_actually_used_to_report_configured(
    db: AsyncSession, user: User, settings: Settings
) -> None:
    """Regression: list_providers used to probe with credentials=None, so a
    user's own stored key was ignored and the provider stayed "not configured"
    even though they had, in fact, configured it."""
    box = SecretBox.from_base64(settings.noema_master_key)
    await CredentialService(db, box, user.id).store(
        "anthropic", "default", "sk-ant-api03-thisisnotarealkey-abcdefghijklmnopqrst"
    )

    providers = await list_providers(user=user, db=db, settings=settings, box=box)

    anthropic = next(p for p in providers if p.name == "anthropic")
    assert anthropic.configured is True
    assert anthropic.capabilities != {}
