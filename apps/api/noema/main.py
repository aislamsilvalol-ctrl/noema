"""NOEMA API application."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from sqlalchemy import text

from noema.api.middleware import install_rate_limiting
from noema.api.v1 import (
    account,
    ai,
    auth,
    concepts,
    library,
    meta,
    notes_actions,
    sources,
    study,
)
from noema.core.config import get_settings
from noema.core.errors import register_error_handlers
from noema.core.logging import configure_logging, get_logger
from noema.core.ratelimit import RateLimiter
from noema.db.base import get_engine

log = get_logger(__name__)

DESCRIPTION = """
NOEMA — open-source adaptive learning platform.

Cookie sessions authenticate the web app; mutations require the CSRF token returned
at login in the `x-csrf-token` header.
""".strip()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(
        settings.noema_log_level, json_output=settings.noema_env != "development"
    )
    settings.validate_for_production()
    log.info("api.starting", env=settings.noema_env, mode=settings.noema_mode.value)
    yield
    await get_engine().dispose()
    redis = getattr(app.state, "redis", None)
    if redis is not None:
        await redis.aclose()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="NOEMA API",
        description=DESCRIPTION,
        version="0.1.0",
        openapi_url="/openapi.json",
        docs_url="/docs",
        lifespan=lifespan,
    )

    # Middleware order is the reverse of registration: Starlette inserts each new
    # layer at the front, so the *last* one added is the outermost. Rate limiting
    # goes first, and therefore innermost, so a 429 still passes back out through
    # the context, header and CORS layers on its way to the client. Registered
    # outermost it would skip CORS, and a browser could not read its own rejection.
    redis = Redis.from_url(settings.redis_url)
    app.state.redis = redis
    install_rate_limiting(app, RateLimiter(redis), settings)

    @app.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(
            request_id=request_id, path=request.url.path
        )
        started = time.perf_counter()
        try:
            response: Response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        response.headers["x-request-id"] = request_id
        response.headers["server-timing"] = (
            f"app;dur={(time.perf_counter() - started) * 1000:.1f}"
        )
        return response

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        response.headers.setdefault("x-content-type-options", "nosniff")
        response.headers.setdefault("x-frame-options", "DENY")
        response.headers.setdefault("referrer-policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "permissions-policy", "geolocation=(), microphone=(), camera=()"
        )
        return response

    # Added last, so it wraps everything above and every response — including one
    # rejected by the rate limiter — carries its CORS headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)

    v1 = APIRouter(prefix="/api/v1")
    v1.include_router(auth.router)
    v1.include_router(account.router)
    v1.include_router(meta.router)
    v1.include_router(library.router)
    v1.include_router(sources.router)
    v1.include_router(sources.search_router)
    v1.include_router(concepts.router)
    v1.include_router(study.router)
    v1.include_router(notes_actions.router)
    v1.include_router(ai.router)
    app.include_router(v1)
    app.include_router(health_router)

    return app


health_router = APIRouter(tags=["health"])


@health_router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@health_router.get("/health/ready")
async def ready() -> dict[str, Any]:
    """Readiness reports each dependency separately.

    A single boolean tells an operator that something is wrong but not what, which is
    the least useful moment to be vague.
    """
    checks: dict[str, Any] = {}
    healthy = True

    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {type(exc).__name__}"
        healthy = False

    settings = get_settings()
    checks["mode"] = settings.noema_mode.value
    checks["default_provider"] = settings.noema_default_provider
    checks["status"] = "ok" if healthy else "degraded"
    return checks


app = create_app()
