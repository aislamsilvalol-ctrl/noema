"""Selection actions on a note: explain, simplify, expand.

`act_on_selection` is tested by calling it directly and draining its
`StreamingResponse`'s body iterator, the same convention `test_db_ai.py` uses for
`chat()` — including reusing its `StreamingFakeProvider`/`collect_sse` helpers.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from noema.api.v1.notes_actions import (
    MAX_SELECTION_CHARS,
    SelectionIn,
    SelectionTooLarge,
    act_on_selection,
)
from noema.core.errors import NotFound
from noema.db.models import Note, Notebook, Subject, User, Workspace
from noema.db.repository import OwnedRepository
from noema.providers.base import (
    Capabilities,
    ChatResponse,
    ProviderError,
    StreamEvent,
)
from noema.providers.gateway import AIGateway
from noema.providers.mock import MockProvider

pytestmark = pytest.mark.asyncio


class StreamingFakeProvider:
    """A scripted ``AIProvider`` whose ``stream()`` yields exactly what's given."""

    name = "fake"
    capabilities = Capabilities(chat=True, streaming=True)

    def __init__(self, events: list[StreamEvent] | Exception) -> None:
        self._events = events

    async def chat(self, request: Any) -> ChatResponse:
        raise NotImplementedError

    async def stream(self, request: Any) -> Any:
        if isinstance(self._events, Exception):
            raise self._events
        for event in self._events:
            yield event

    async def embed(self, request: Any) -> Any:
        raise NotImplementedError

    async def structured(self, request: Any) -> dict[str, Any]:
        raise NotImplementedError

    async def health(self) -> Any:
        raise NotImplementedError


async def collect_sse(body: Any) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    async for chunk in body:
        text = chunk.decode() if isinstance(chunk, bytes) else chunk
        lines = text.strip("\n").split("\n")
        name = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        events.append((name, data))
    return events


@pytest.fixture
async def note(db: AsyncSession, user: User) -> Note:
    workspace = await OwnedRepository(db, Workspace, user.id).create(
        title="Bio", slug=f"bio-{uuid.uuid4().hex[:8]}"
    )
    subject = await OwnedRepository(db, Subject, user.id).create(
        workspace_id=workspace.id, title="Cells", slug=f"cells-{uuid.uuid4().hex[:8]}"
    )
    notebook = await OwnedRepository(db, Notebook, user.id).create(
        subject_id=subject.id,
        title="Cell Biology",
        slug=f"cb-{uuid.uuid4().hex[:8]}",
        retrieval_settings={},
    )
    return await OwnedRepository(db, Note, user.id).create(
        notebook_id=notebook.id,
        title="Mitochondria",
        content_md="The mitochondria is the powerhouse of the cell.",
    )


async def test_a_selection_is_explained_by_streaming_tokens(
    db: AsyncSession, user: User, note: Note
) -> None:
    gateway = AIGateway(MockProvider())

    response = await act_on_selection(
        note.id,
        "explain",
        SelectionIn(text="powerhouse of the cell"),
        user=user,
        db=db,
        gateway=gateway,
    )
    events = await collect_sse(response.body_iterator)

    assert events[-1][0] == "done"
    assert events[-1][1]["action"] == "explain"
    assert any(name == "token" for name, _ in events)


async def test_a_selection_over_the_limit_is_refused(
    db: AsyncSession, user: User, note: Note
) -> None:
    gateway = AIGateway(MockProvider())
    oversized = "x" * (MAX_SELECTION_CHARS + 1)

    with pytest.raises(SelectionTooLarge, match=str(MAX_SELECTION_CHARS)):
        await act_on_selection(
            note.id,
            "explain",
            SelectionIn(text=oversized),
            user=user,
            db=db,
            gateway=gateway,
        )


async def test_a_selection_right_at_the_limit_is_accepted(
    db: AsyncSession, user: User, note: Note
) -> None:
    gateway = AIGateway(MockProvider())
    exactly = "x" * MAX_SELECTION_CHARS

    response = await act_on_selection(
        note.id,
        "explain",
        SelectionIn(text=exactly),
        user=user,
        db=db,
        gateway=gateway,
    )
    events = await collect_sse(response.body_iterator)

    assert events[-1][0] == "done"


async def test_acting_on_another_users_note_is_refused(
    db: AsyncSession, other_user: User, note: Note
) -> None:
    gateway = AIGateway(MockProvider())

    with pytest.raises(NotFound):
        await act_on_selection(
            note.id,
            "explain",
            SelectionIn(text="powerhouse of the cell"),
            user=other_user,
            db=db,
            gateway=gateway,
        )


async def test_a_mid_stream_provider_error_becomes_an_error_event(
    db: AsyncSession, user: User, note: Note
) -> None:
    gateway = AIGateway(
        StreamingFakeProvider(ProviderError("down", provider="fake", retryable=False))
    )

    response = await act_on_selection(
        note.id,
        "simplify",
        SelectionIn(text="powerhouse of the cell"),
        user=user,
        db=db,
        gateway=gateway,
    )
    events = await collect_sse(response.body_iterator)

    assert events[-1][0] == "error"
    assert events[-1][1]["provider"] == "fake"


async def test_the_note_is_never_modified_by_an_action(
    db: AsyncSession, user: User, note: Note
) -> None:
    original = note.content_md
    gateway = AIGateway(MockProvider())

    response = await act_on_selection(
        note.id,
        "expand",
        SelectionIn(text="powerhouse of the cell"),
        user=user,
        db=db,
        gateway=gateway,
    )
    async for _ in response.body_iterator:
        pass

    await db.refresh(note)
    assert note.content_md == original
