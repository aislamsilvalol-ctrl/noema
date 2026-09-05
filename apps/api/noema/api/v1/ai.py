"""AI endpoints: tutor chat, the Professor (V3), sessions, providers, BYOK, usage."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import asdict

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

from noema.api.v1 import deps
from noema.api.v1.schemas import (
    ChatIn,
    CredentialCreate,
    CredentialOut,
    ProviderOut,
    TeachingSessionOut,
    TeachingTurnOut,
    UsageOut,
)
from noema.core.errors import QuotaExceeded
from noema.core.logging import get_logger
from noema.db.models import Notebook, TeachingSession
from noema.db.repository import OwnedRepository
from noema.professor.blocks import Block
from noema.professor.engine import LearningEvent, ProfessorEngine
from noema.prompts import Prompt, load, tutor
from noema.providers.base import ChatRequest, Message, ProviderError, Role, TaskClass
from noema.providers.registry import available
from noema.retrieval.grounding import (
    CitationFilter,
    build_context,
    citations_for,
    used_citations,
)
from noema.retrieval.search import Retrieved, retrieve
from noema.retrieval.search import has_material as notebook_has_material
from noema.services.credentials import CredentialService
from noema.services.entitlements import EntitlementsService
from noema.services.teaching_session import TeachingSessions
from noema.services.usage import usage_by_task

log = get_logger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[Depends(deps.require_csrf)])


@router.post("/chat")
async def chat(
    payload: ChatIn,
    user: deps.CurrentUser,
    db: deps.SessionDep,
    gateway: deps.GatewayDep,
    settings: deps.SettingsDep,
) -> StreamingResponse:
    """Stream a tutor reply as Server-Sent Events.

    With a notebook, the reply is grounded: chunks are retrieved, numbered into the
    prompt, and every citation is validated on the way out. Without one, it is an
    ordinary tutor conversation.
    """
    if payload.notebook_id is not None:
        await OwnedRepository(db, Notebook, user.id).get(payload.notebook_id)

    question = payload.messages[-1].content
    results: list[Retrieved] = []
    grounded = payload.notebook_id is not None and payload.grounded

    has_material = True
    if grounded:
        results = await retrieve(
            db,
            question,
            owner_id=user.id,
            notebook_id=payload.notebook_id,
            gateway=gateway,
            embedding_model=settings.noema_embedding_model,
        )
        if not results and payload.notebook_id is not None:
            has_material = await notebook_has_material(
                db, owner_id=user.id, notebook_id=payload.notebook_id
            )

    system, context_block, cited = _assemble(
        payload.mode, grounded, results, has_material
    )
    citations = citations_for(cited)

    messages = [Message(role=Role.SYSTEM, content=system.body)]
    messages += [Message(role=Role(m.role), content=m.content) for m in payload.messages]
    if context_block:
        messages.append(
            Message(
                role=Role.USER,
                content=f"<MATERIALS>\n{context_block}\n</MATERIALS>",
            )
        )

    request = ChatRequest(
        messages=messages,
        task=TaskClass.TUTOR_CHAT,
        metadata={
            "mode": payload.mode,
            "grounded": grounded,
            "retrieved": len(cited),
            "prompt_version": system.version,
        },
    )

    async def events() -> AsyncIterator[bytes]:
        # The filter buffers to sentence boundaries so a citation can be checked
        # before the user reads the claim that carries it.
        citation_filter = CitationFilter.for_results(cited)

        if citations:
            yield _sse("sources", {"citations": [asdict(c) for c in citations]})

        try:
            async for event in gateway.stream(request):
                if event.delta:
                    safe = citation_filter.feed(event.delta)
                    if safe:
                        yield _sse("token", {"text": safe})
                if event.done:
                    tail = citation_filter.flush()
                    if tail:
                        yield _sse("token", {"text": tail})

                    if citation_filter.dropped:
                        log.warning(
                            "chat.citations_invented",
                            count=len(citation_filter.dropped),
                            notebook_id=str(payload.notebook_id),
                        )

                    yield _sse(
                        "done",
                        {
                            "prompt_tokens": event.usage.prompt_tokens
                            if event.usage
                            else 0,
                            "completion_tokens": (
                                event.usage.completion_tokens if event.usage else 0
                            ),
                            "grounded": grounded,
                            "used_citations": [
                                asdict(c)
                                for c in used_citations(citations, citation_filter.used)
                            ],
                            "dropped_sentences": len(citation_filter.dropped),
                        },
                    )
        except ProviderError as exc:
            # The stream has already been accepted, so a mid-stream failure has to be
            # reported inside the stream rather than as a status code.
            log.warning("chat.stream_failed", provider=exc.provider, error=str(exc))
            yield _sse("error", {"message": str(exc), "provider": exc.provider})
        except QuotaExceeded as exc:
            # Same reasoning as ProviderError above: register_error_handlers can no
            # longer intervene once this generator is already streaming.
            log.warning("chat.stream_budget_exhausted", task=TaskClass.TUTOR_CHAT.value)
            yield _sse("error", {"message": exc.detail})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
    )


@router.post("/professor")
async def professor_chat(
    payload: ChatIn,
    user: deps.CurrentUser,
    db: deps.SessionDep,
    gateway: deps.GatewayDep,
    settings: deps.SettingsDep,
    box: deps.SecretBoxDep,
) -> StreamingResponse:
    """Stream one turn of the Professor (V3).

    Additive to ``chat()`` above — ``POST /ai/chat`` stays the direct,
    manual-``mode`` path. Here the server decides: it finds or starts the
    learning journey (goal → curriculum), records the learning event the
    client sent, chooses the move before any model speaks, assembles the
    prompt from *stored* state under a token budget, and streams the reply
    as prose plus structured events (``block``, ``mino``, ``flashcards``,
    ``checkpoint``, ``mastery``, ``memory``). See ``noema/professor/``.
    """
    if payload.notebook_id is not None:
        await OwnedRepository(db, Notebook, user.id).get(payload.notebook_id)

    gate = await EntitlementsService(db, user).check_ai_usage()
    if not gate.allowed:
        # Checked before anything is stored or called -- a blocked turn should
        # cost the platform nothing. Notes and materials stay reachable.
        async def blocked() -> AsyncIterator[bytes]:
            yield _sse(
                "blocked",
                {"used_units": gate.used_units, "limit_units": gate.limit_units},
            )

        return StreamingResponse(
            blocked(),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
        )

    question = payload.messages[-1].content
    credentials = CredentialService(db, box, user.id)

    # The lesson this message belongs to. Written down before anything is
    # classified or streamed, so a learner who returns tomorrow finds today.
    sessions = TeachingSessions(db, user.id)
    resumed = await sessions.start_or_resume(
        session_id=payload.session_id,
        notebook_id=payload.notebook_id,
        learning_goal=question,
    )
    session = resumed.session
    await sessions.record_learner(session, question)
    # Committed here, not at the end of the request. The request's own
    # transaction otherwise stays open for the whole stream, holding the
    # UPDATE lock on this session row — so the Noema turn, written on a
    # separate connection after `done`, cannot see a session created in this
    # request, and the *next* message's UPDATE waits on this one until the
    # stream ends. Both were observed in production; this is the fix.
    await db.commit()

    from noema.api.v1.deps import build_provider

    engine = ProfessorEngine(
        db,
        user=user,
        settings=settings,
        gateway=gateway,
        credentials=credentials,
        build_provider=build_provider,
    )
    event = payload.learning_event
    prepared = await engine.prepare(
        session=session,
        question=question,
        created=resumed.created,
        notebook_id=payload.notebook_id,
        grounded_wanted=payload.grounded,
        event=LearningEvent(
            kind=event.kind,
            concept=event.concept,
            correct=event.correct,
            score=event.score,
            question=event.question,
            chosen=event.chosen,
            assessment_id=event.assessment_id,
        )
        if event is not None
        else None,
    )
    # The journey, the routing bookkeeping and any pre-work (cards, a
    # checkpoint) are durable before the first token, for the same reason.
    await db.commit()

    async def events() -> AsyncIterator[bytes]:
        if gate.warn:
            yield _sse(
                "warning",
                {"used_units": gate.used_units, "limit_units": gate.limit_units},
            )
        yield _sse("session", {"id": str(session.id), "created": resumed.created})
        async for chunk in engine.stream(prepared, session=session, question=question):
            yield chunk

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
    )


@router.get("/sessions/latest", response_model=TeachingSessionOut | None)
async def latest_session(
    user: deps.CurrentUser,
    db: deps.SessionDep,
    notebook_id: uuid.UUID | None = None,
) -> TeachingSessionOut | None:
    """Where the learner left off — the home screen's "Continue learning"."""
    sessions = TeachingSessions(db, user.id)
    session = await sessions.latest_open(notebook_id=notebook_id)
    if session is None:
        return None
    return await _session_out(sessions, session)


@router.get("/sessions/{session_id}", response_model=TeachingSessionOut)
async def get_session(
    session_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> TeachingSessionOut:
    """A lesson, resumed: its state and transcript, oldest turn first."""
    sessions = TeachingSessions(db, user.id)
    session = await sessions.sessions.get(session_id)
    return await _session_out(sessions, session)


async def _session_out(
    sessions: TeachingSessions, session: TeachingSession
) -> TeachingSessionOut:
    turns = await sessions.history(session)
    return TeachingSessionOut(
        id=session.id,
        notebook_id=session.notebook_id,
        journey_id=session.journey_id,
        learning_goal=session.learning_goal,
        subject=session.subject,
        current_topic=session.current_topic,
        current_concept=session.current_concept,
        plan=list(session.plan or []),
        turn_count=session.turn_count,
        last_turn_at=session.last_turn_at,
        ended_at=session.ended_at,
        turns=[
            TeachingTurnOut(
                role=turn.role.value,
                content=turn.content,
                intent=turn.intent,
                created_at=turn.created_at,
                blocks=[
                    Block(tool=b["tool"], data=b["data"]).public() | {"tool": b["tool"]}
                    for b in (turn.blocks or [])
                    if isinstance(b, dict) and "tool" in b and "data" in b
                ]
                or None,
            )
            for turn in turns
        ],
    )


@router.get("/providers", response_model=list[ProviderOut])
async def list_providers(
    user: deps.CurrentUser,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
    box: deps.SecretBoxDep,
) -> list[ProviderOut]:
    from noema.api.v1.deps import build_provider

    credentials = CredentialService(db, box, user.id)
    stored = {c.provider for c in await credentials.list()}
    deployment_keys = {
        "anthropic": bool(settings.anthropic_api_key),
        "openai": bool(settings.openai_api_key),
        "gemini": bool(settings.gemini_api_key),
        "openrouter": bool(settings.openrouter_api_key),
        "ollama": True,
        "mock": True,
    }

    out: list[ProviderOut] = []
    for name in available(local_mode=settings.is_local_mode):
        configured = name in stored or deployment_keys.get(name, False)
        capabilities: dict[str, object] = {}
        if configured:
            try:
                provider = await build_provider(name, settings, credentials)
                capabilities = asdict(provider.capabilities)
            except Exception:
                configured = False

        out.append(
            ProviderOut(
                name=name,
                configured=configured,
                capabilities=capabilities,
                is_default=name == settings.noema_default_provider,
            )
        )
    return out


@router.get("/credentials", response_model=list[CredentialOut])
async def list_credentials(
    user: deps.CurrentUser, db: deps.SessionDep, box: deps.SecretBoxDep
) -> list[CredentialOut]:
    summaries = await CredentialService(db, box, user.id).list()
    return [CredentialOut(**asdict(s)) for s in summaries]


@router.post(
    "/credentials", response_model=CredentialOut, status_code=status.HTTP_201_CREATED
)
async def create_credential(
    payload: CredentialCreate,
    user: deps.CurrentUser,
    db: deps.SessionDep,
    box: deps.SecretBoxDep,
    settings: deps.SettingsDep,
) -> CredentialOut:
    service = CredentialService(db, box, user.id)
    summary = await service.store(payload.provider, payload.label, payload.api_key)

    # Validate immediately: a revoked or mistyped key should fail here with a clear
    # message, not silently mid-session three days later.
    from noema.api.v1.deps import build_provider

    try:
        provider = await build_provider(payload.provider, settings, service)
        report = await provider.health()
        summary = await service.mark_verified(
            summary.id, error=None if report.healthy else report.detail
        )
    except Exception as exc:
        summary = await service.mark_verified(summary.id, error=str(exc)[:300])

    return CredentialOut(**asdict(summary))


@router.delete("/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential(
    credential_id: uuid.UUID,
    user: deps.CurrentUser,
    db: deps.SessionDep,
    box: deps.SecretBoxDep,
) -> None:
    await CredentialService(db, box, user.id).delete(credential_id)


@router.get("/usage", response_model=list[UsageOut])
async def usage(
    user: deps.CurrentUser, db: deps.SessionDep, days: int = 30
) -> list[UsageOut]:
    rows = await usage_by_task(db, user.id, days=days)
    return [
        UsageOut(
            task=task,
            provider=provider,
            prompt_tokens=int(prompt or 0),
            completion_tokens=int(completion or 0),
            cost_cents=float(cost or 0.0),
        )
        for task, provider, prompt, completion, cost in rows
    ]


def _assemble(
    mode: str, grounded: bool, results: list[Retrieved], has_material: bool = True
) -> tuple[Prompt, str, list[Retrieved]]:
    """Choose the prompt and build the context for this turn.

    Four cases: grounded with material found; grounded with nothing found in
    an otherwise-populated notebook (an honest refusal is the right answer);
    grounded but the notebook has nothing chunked at all yet, which falls
    back to the ordinary tutor path -- a brand-new, empty notebook is not
    "materials that don't cover this," there simply are no materials yet, and
    the honest thing is to teach from general knowledge until some exist, the
    same way a notebook-less turn already does; and an ordinary tutor turn
    outside any notebook. ``has_material`` only matters when ``results`` is
    empty, so callers that never disambiguate it (nothing calls this with
    ``grounded=True`` and skips the check) can rely on the default.
    """
    if not grounded:
        return tutor(mode), "", []
    if not results:
        if not has_material:
            return tutor(mode), "", []
        return load("rag.no_context"), "", []

    context_block, included = build_context(results)
    return load("rag.answer"), context_block, included


def _sse(event: str, data: dict[str, object]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()
