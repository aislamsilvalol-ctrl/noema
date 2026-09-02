"""AI endpoints: streaming tutor chat, provider inventory, BYOK credentials, usage."""

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
    UsageOut,
)
from noema.core.errors import Conflict, QuotaExceeded
from noema.core.logging import get_logger
from noema.db.models import ModelTier, Notebook
from noema.db.repository import OwnedRepository
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
from noema.services import professor
from noema.services.credentials import CredentialService
from noema.services.entitlements import EntitlementsService
from noema.services.professor import DispatchPlan, Intent
from noema.services.professor_memory import build_memory as build_professor_memory
from noema.services.usage import usage_by_task
from noema.study.exam import start_exam
from noema.study.generation import generate_cards
from noema.study.questions import generate_questions

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
    """Stream a Professor Noema reply: classify the message, then dispatch.

    Additive to ``chat()`` above, not a replacement for it — ``POST /ai/chat``
    is untouched and stays the direct, manual-``mode`` path a caller can
    still use. This route decides the mode itself instead of trusting one,
    picking a cost tier per decision the way ``noema/services/professor.py``'s
    module docstring describes: classification always on the cheapest
    configured tier, the decided action on whatever tier that action deserves.
    """
    if payload.notebook_id is not None:
        await OwnedRepository(db, Notebook, user.id).get(payload.notebook_id)

    gate = await EntitlementsService(db, user).check_ai_usage()
    if not gate.allowed:
        # Checked before the (cheap, but real) classification call below --
        # a blocked turn should cost the platform nothing, not just skip the
        # dispatched action. Existing notes/materials stay fully reachable;
        # only new Professor turns are gated.
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

    from noema.api.v1.deps import build_provider

    economy = await professor.tiered_gateway(
        ModelTier.ECONOMY,
        db=db,
        default_gateway=gateway,
        build_provider=build_provider,
        settings=settings,
        credentials=credentials,
    )
    intent = await professor.classify_intent(
        economy.gateway, question, model=economy.model
    )
    if professor.needs_notebook_material(intent, payload.notebook_id):
        # Honest boundary: there is nothing to quiz or card without a notebook
        # to draw from. Fall back to the conversation itself rather than fail
        # a message that was never wrong, just under-specified.
        intent = Intent.EXPLAIN

    dispatch = await professor.plan(
        intent,
        db=db,
        default_gateway=gateway,
        build_provider=build_provider,
        settings=settings,
        credentials=credentials,
    )

    async def events() -> AsyncIterator[bytes]:
        if gate.warn:
            yield _sse(
                "warning",
                {"used_units": gate.used_units, "limit_units": gate.limit_units},
            )
        yield _sse("intent", {"intent": dispatch.intent.value})

        if dispatch.intent is Intent.CREATE_EXAM:
            async for event in _dispatch_exam(dispatch, payload, user, db):
                yield event
            return

        if dispatch.intent in (Intent.QUIZ_ME, Intent.CREATE_FLASHCARD):
            async for event in _dispatch_action(dispatch, payload, user, db):
                yield event
            return

        async for event in _dispatch_stream(
            dispatch, payload, question, user, db, settings
        ):
            yield event

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
    )


async def _dispatch_action(
    dispatch: DispatchPlan,
    payload: ChatIn,
    user: deps.CurrentUser,
    db: deps.SessionDep,
) -> AsyncIterator[bytes]:
    """Runs a generation action (quiz/flashcard) and reports what got made.

    ``payload.notebook_id`` is guaranteed non-``None`` here —
    ``needs_notebook_material`` already redirected anything without one back
    to ``EXPLAIN`` before a plan naming this dispatch could ever be built.
    """
    notebook_id = payload.notebook_id
    assert notebook_id is not None

    # generate_questions/generate_cards already catch ProviderError per batch and
    # degrade to fewer (or zero) items -- that's a deliberate design for a
    # provider hiccup. QuotaExceeded means something different (the budget is
    # gone, retrying or continuing is pointless) and isn't caught by either, so
    # it must be handled here or the stream dies with no error event, the exact
    # gap register_error_handlers can no longer close once streaming has begun.
    try:
        if dispatch.intent is Intent.QUIZ_ME:
            questions = await generate_questions(
                db,
                notebook_id,
                owner_id=user.id,
                gateway=dispatch.call.gateway,
                limit=3,
                model=dispatch.call.model,
            )
            yield _sse(
                "action",
                {
                    "intent": dispatch.intent.value,
                    "count": len(questions),
                    "items": [{"id": str(q.id), "prompt": q.prompt} for q in questions],
                },
            )
        else:
            cards = await generate_cards(
                db,
                notebook_id,
                owner_id=user.id,
                gateway=dispatch.call.gateway,
                limit=3,
                model=dispatch.call.model,
            )
            yield _sse(
                "action",
                {
                    "intent": dispatch.intent.value,
                    "count": len(cards),
                    "items": [{"id": str(c.id), "front": c.front_md} for c in cards],
                },
            )
    except QuotaExceeded as exc:
        log.warning("professor.action_budget_exhausted", task=dispatch.task.value)
        yield _sse("error", {"message": exc.detail})
        return
    yield _sse("done", {"grounded": True})


async def _dispatch_exam(
    dispatch: DispatchPlan,
    payload: ChatIn,
    user: deps.CurrentUser,
    db: deps.SessionDep,
) -> AsyncIterator[bytes]:
    """Starts a real, sittable exam over the notebook's existing questions.

    Calls ``start_exam()`` unchanged, deliberately — it picks questions at
    random rather than weighted toward weak concepts, on purpose: its own
    docstring explains an exam that quietly asks you what you are worst at is
    a drill, not an exam, and its score stops being comparable across
    sittings. A "difficulty-targeted" exam would undermine that invariant, so
    this dispatch does not attempt one; "dificuldades"/"nível desejado" from
    the student's request stay signals for *whether* to suggest an exam
    (the classifier's job) or a review/drill instead, not inputs that reshape
    which questions this specific exam contains.

    Fixed defaults (10 questions, 20 minutes) match ``ExamStart``'s own
    schema defaults in ``study.py`` — the message that triggered this intent
    is not parsed for a requested size; that is a reasonable later
    refinement, not a gap this phase needs to close to be real and useful.

    ``payload.notebook_id`` is guaranteed non-``None`` here —
    ``needs_notebook_material`` already redirected anything without one back
    to ``EXPLAIN`` before a plan naming this dispatch could ever be built.
    """
    notebook_id = payload.notebook_id
    assert notebook_id is not None

    try:
        exam = await start_exam(db, notebook_id, owner_id=user.id, count=10, minutes=20)
    except Conflict as exc:
        # The stream has already been accepted, so this has to be reported
        # inside it rather than as a 409 — same reasoning as ProviderError
        # below in _dispatch_stream.
        yield _sse("error", {"message": str(exc)})
        return

    yield _sse(
        "action",
        {
            "intent": dispatch.intent.value,
            "count": 1,
            "items": [],
            "exam_id": str(exam.id),
            "minutes": exam.minutes,
        },
    )
    yield _sse("done", {"grounded": True})


async def _dispatch_stream(
    dispatch: DispatchPlan,
    payload: ChatIn,
    question: str,
    user: deps.CurrentUser,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
) -> AsyncIterator[bytes]:
    """EXPLAIN / DEEPEN / SUMMARIZE all stream a tutor-chat-shaped reply.

    Structurally mirrors ``chat()``'s own streaming loop above — kept as its
    own copy rather than a shared helper, on purpose: refactoring that route
    to share code with a brand-new one this early risks destabilising a
    tested, working path for a program still finding its shape. Worth
    revisiting once the orchestrator's own shape has settled.
    """
    results: list[Retrieved] = []
    grounded = payload.notebook_id is not None and payload.grounded
    has_material = True

    if grounded:
        results = await retrieve(
            db,
            question,
            owner_id=user.id,
            notebook_id=payload.notebook_id,
            gateway=dispatch.call.gateway,
            embedding_model=settings.noema_embedding_model,
        )
        if not results and payload.notebook_id is not None:
            has_material = await notebook_has_material(
                db, owner_id=user.id, notebook_id=payload.notebook_id
            )

    system, context_block, cited = _assemble(
        dispatch.mode, grounded, results, has_material
    )
    citations = citations_for(cited)

    messages = [Message(role=Role.SYSTEM, content=system.body)]
    messages += [Message(role=Role(m.role), content=m.content) for m in payload.messages]
    if context_block:
        messages.append(
            Message(role=Role.USER, content=f"<MATERIALS>\n{context_block}\n</MATERIALS>")
        )

    # Selective memory (mastery + open misconceptions for this notebook's own
    # concepts), only for the two intents that actually teach -- SUMMARIZE
    # condenses what's in front of it and doesn't need what the student
    # already knows. Only EXPLAIN/DEEPEN reach here with a task worth this.
    if payload.notebook_id is not None and dispatch.intent in (
        Intent.EXPLAIN,
        Intent.DEEPEN,
    ):
        memory = await build_professor_memory(
            db, owner_id=user.id, notebook_id=payload.notebook_id
        )
        rendered = memory.render()
        if rendered:
            messages.append(
                Message(
                    role=Role.USER,
                    content=f"<STUDENT_MEMORY>\n{rendered}\n</STUDENT_MEMORY>",
                )
            )

    request = ChatRequest(
        messages=messages,
        task=dispatch.task,
        model=dispatch.call.model,
        metadata={
            "mode": dispatch.mode,
            "intent": dispatch.intent.value,
            "grounded": grounded,
            "retrieved": len(cited),
            "prompt_version": system.version,
        },
    )

    citation_filter = CitationFilter.for_results(cited)

    if citations:
        yield _sse("sources", {"citations": [asdict(c) for c in citations]})

    try:
        async for event in dispatch.call.gateway.stream(request):
            if event.delta:
                safe = citation_filter.feed(event.delta)
                if safe:
                    yield _sse("token", {"text": safe})
            if event.done:
                tail = citation_filter.flush()
                if tail:
                    yield _sse("token", {"text": tail})
                yield _sse(
                    "done",
                    {
                        "prompt_tokens": event.usage.prompt_tokens if event.usage else 0,
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
        log.warning("professor.stream_failed", provider=exc.provider, error=str(exc))
        yield _sse("error", {"message": str(exc), "provider": exc.provider})
    except QuotaExceeded as exc:
        # Same reasoning as ProviderError above: register_error_handlers can no
        # longer intervene once this generator is already streaming.
        log.warning("professor.stream_budget_exhausted", task=dispatch.task.value)
        yield _sse("error", {"message": exc.detail})


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
