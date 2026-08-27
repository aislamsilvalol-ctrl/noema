"""Selection actions on a note.

The user selects a passage and asks for it to be explained, simplified or expanded.
Results stream back and are **never written into the note** — what the learner wrote
stays theirs, and an assistant that silently edits your notes is one you stop
trusting.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from noema.api.v1 import deps
from noema.core.errors import NoemaError
from noema.core.logging import get_logger
from noema.db.models import Note
from noema.db.repository import OwnedRepository
from noema.prompts import load
from noema.providers.base import ChatRequest, Message, ProviderError, Role, TaskClass

log = get_logger(__name__)

router = APIRouter(
    prefix="/notes", tags=["notes"], dependencies=[Depends(deps.require_csrf)]
)

Action = Literal["explain", "simplify", "expand"]

#: Simplifying is a rewrite, not a conversation, so it routes to the cheap model.
ACTION_TASKS: dict[Action, TaskClass] = {
    "explain": TaskClass.TUTOR_CHAT,
    "simplify": TaskClass.SUMMARIZE,
    "expand": TaskClass.TUTOR_CHAT,
}

MAX_SELECTION_CHARS = 8_000
CONTEXT_CHARS = 2_000


class SelectionTooLarge(NoemaError):
    slug = "selection-too-large"
    title = "Selection too large"


class SelectionIn(BaseModel):
    # No max_length here on purpose: Pydantic would reject an oversized
    # selection before this route ever ran, with a generic field-validation
    # error instead of the friendlier SelectionTooLarge below — checked
    # explicitly in the route body instead.
    text: str = Field(min_length=1)


@router.post("/{note_id}/actions/{action}")
async def act_on_selection(
    note_id: uuid.UUID,
    action: Action,
    payload: SelectionIn,
    user: deps.CurrentUser,
    db: deps.SessionDep,
    gateway: deps.GatewayDep,
) -> StreamingResponse:
    if len(payload.text) > MAX_SELECTION_CHARS:
        raise SelectionTooLarge(
            f"That selection is {len(payload.text)} characters; "
            f"the limit is {MAX_SELECTION_CHARS}. Select a shorter passage."
        )

    note = await OwnedRepository(db, Note, user.id).get(note_id)
    prompt = load(f"note.{action}")

    # The note around the selection is context, not instructions. It is the user's
    # own writing, but it is still untrusted input to the model.
    context = note.content_md[:CONTEXT_CHARS]
    user_message = (
        f"<note title={note.title!r}>\n{context}\n</note>\n\n"
        f"<selection>\n{payload.text}\n</selection>"
    )

    request = ChatRequest(
        messages=[
            Message(role=Role.SYSTEM, content=prompt.body),
            Message(role=Role.USER, content=user_message),
        ],
        task=ACTION_TASKS[action],
        metadata={
            "action": action,
            "note_id": str(note_id),
            "prompt_version": prompt.version,
        },
    )

    async def events() -> AsyncIterator[bytes]:
        try:
            async for event in gateway.stream(request):
                if event.delta:
                    yield _sse("token", {"text": event.delta})
                if event.done:
                    yield _sse("done", {"action": action})
        except ProviderError as exc:
            log.warning("note_action.failed", action=action, provider=exc.provider)
            yield _sse("error", {"message": str(exc), "provider": exc.provider})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
    )


def _sse(event: str, data: dict[str, object]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()
