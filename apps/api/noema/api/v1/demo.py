"""The landing page's demo lesson: thirty seconds of real teaching, no account.

`POST /ai/demo` takes one subject and streams the opening of a lesson from
the deployment's own cheapest configured model. It is deliberately narrow:
no history, no retrieval, no session, a hard token cap, and a per-caller
daily allowance on top of the global rate limit — so a public page can prove
the product without being able to spend the budget. When the model is not
available the client falls back to its written sample; this endpoint says so
with a normal problem response rather than a broken stream.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, StringConstraints

from noema.api.middleware import client_key
from noema.api.v1 import deps
from noema.core.errors import ProviderUnavailable, RateLimited
from noema.core.logging import get_logger
from noema.core.ratelimit import RateLimiter
from noema.prompts import load
from noema.providers.base import ChatRequest, Message, ProviderError, Role, TaskClass
from noema.providers.gateway import AIGateway

log = get_logger(__name__)
router = APIRouter(prefix="/ai", tags=["ai"])

DAY = 24 * 60 * 60


class DemoIn(BaseModel):
    subject: Annotated[
        str, StringConstraints(min_length=1, max_length=120, strip_whitespace=True)
    ]


def _sse(event: str, data: dict[str, object]) -> bytes:
    import json

    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


async def stream_demo(
    subject: str, gateway: AIGateway, *, model: str | None, max_tokens: int
) -> AsyncIterator[bytes]:
    """The lesson opening, as SSE — the same `token`/`done`/`error` shape the app uses."""
    prompt = load("demo.teach")
    request = ChatRequest(
        messages=[
            Message(role=Role.SYSTEM, content=prompt.body),
            Message(role=Role.USER, content=subject),
        ],
        task=TaskClass.TUTOR_CHAT,
        model=model,
        max_tokens=max_tokens,
        metadata={"mode": "demo", "prompt_version": prompt.version},
    )
    try:
        async for event in gateway.stream(request):
            if event.delta:
                yield _sse("token", {"text": event.delta})
            if event.done:
                yield _sse("done", {})
    except ProviderError as exc:
        log.warning("demo.stream_failed", provider=exc.provider, error=str(exc))
        yield _sse("error", {"message": "unavailable", "provider": exc.provider})


@router.post("/demo")
async def demo_teach(
    payload: DemoIn, request: Request, settings: deps.SettingsDep
) -> StreamingResponse:
    if not settings.noema_demo_enabled:
        raise ProviderUnavailable("The demo is switched off on this deployment.")

    # A small daily allowance per caller, on top of the global per-minute
    # limit. Absent Redis (tests, local runs without it) the allowance is not
    # enforced — the global limiter is equally absent there.
    redis = getattr(request.app.state, "redis", None)
    if redis is not None:
        decision = await RateLimiter(redis, prefix="noema:demo").check(
            client_key(request, settings.noema_trusted_proxy_hops),
            limit=settings.noema_demo_per_caller_per_day,
            period=DAY,
        )
        if not decision.allowed:
            raise RateLimited(
                "That is all the demo lessons for today. Sign in to keep learning.",
                retry_after=decision.reset_after,
            )

    try:
        provider = await deps.build_provider(
            settings.noema_default_provider, settings, None
        )
    except Exception as exc:
        log.warning("demo.provider_unavailable", error=str(exc))
        raise ProviderUnavailable("The demo tutor is unavailable right now.") from exc

    return StreamingResponse(
        stream_demo(
            payload.subject,
            AIGateway(provider),
            model=settings.noema_demo_model or None,
            max_tokens=settings.noema_demo_max_tokens,
        ),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
    )
