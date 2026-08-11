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
from noema.core.logging import get_logger
from noema.db.models import Notebook
from noema.db.repository import OwnedRepository
from noema.prompts import tutor
from noema.providers.base import ChatRequest, Message, ProviderError, Role, TaskClass
from noema.providers.registry import available
from noema.services.credentials import CredentialService
from noema.services.usage import usage_by_task

log = get_logger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[Depends(deps.require_csrf)])


@router.post("/chat")
async def chat(
    payload: ChatIn,
    user: deps.CurrentUser,
    db: deps.SessionDep,
    gateway: deps.GatewayDep,
) -> StreamingResponse:
    """Stream a tutor reply as Server-Sent Events.

    Phase 1 answers from the conversation alone. Phase 2 injects retrieved chunks and
    the citation contract; the transport does not change, so the client written
    against this endpoint keeps working.
    """
    if payload.notebook_id is not None:
        await OwnedRepository(db, Notebook, user.id).get(payload.notebook_id)

    system = tutor(payload.mode)
    request = ChatRequest(
        messages=[
            Message(role=Role.SYSTEM, content=system.body),
            *(Message(role=Role(m.role), content=m.content) for m in payload.messages),
        ],
        task=TaskClass.TUTOR_CHAT,
        metadata={"mode": payload.mode, "prompt_version": system.version},
    )

    async def events() -> AsyncIterator[bytes]:
        try:
            async for event in gateway.stream(request):
                if event.delta:
                    yield _sse("token", {"text": event.delta})
                if event.done:
                    yield _sse(
                        "done",
                        {
                            "prompt_tokens": event.usage.prompt_tokens
                            if event.usage
                            else 0,
                            "completion_tokens": (
                                event.usage.completion_tokens if event.usage else 0
                            ),
                        },
                    )
        except ProviderError as exc:
            # The stream has already been accepted, so a mid-stream failure has to be
            # reported inside the stream rather than as a status code.
            log.warning("chat.stream_failed", provider=exc.provider, error=str(exc))
            yield _sse("error", {"message": str(exc), "provider": exc.provider})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
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
                provider = await build_provider(name, settings, None)
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


def _sse(event: str, data: dict[str, object]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()
