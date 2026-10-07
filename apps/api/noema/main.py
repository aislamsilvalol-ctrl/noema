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
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from noema.api.middleware import install_rate_limiting
from noema.api.v1 import (
    account,
    admin,
    ai,
    auth,
    billing,
    concepts,
    demo,
    exports,
    feedback,
    focus,
    imports,
    journeys,
    library,
    meta,
    notes_actions,
    progression,
    security,
    sources,
    study,
    tokens,
)
from noema.core.config import get_settings
from noema.core.errors import register_error_handlers
from noema.core.health import readiness
from noema.core.logging import configure_logging, get_logger
from noema.core.ratelimit import RateLimiter
from noema.db.base import get_engine
from noema.plugins import load_plugins

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
    # After the built-ins (imported transitively above), never before them — a
    # broken plugin must not be able to take a working provider down with it.
    load_plugins()
    yield
    await get_engine().dispose()
    redis = getattr(app.state, "redis", None)
    if redis is not None:
        await redis.aclose()


def create_app() -> FastAPI:
    settings = get_settings()

    # The interactive docs are a development convenience. In production the
    # schema is not published: a route inventory is reconnaissance handed to
    # anyone who asks, and the web app never reads it.
    serve_docs = settings.noema_env != "production"
    app = FastAPI(
        title="NOEMA API",
        description=DESCRIPTION,
        version="0.1.0",
        openapi_url="/openapi.json" if serve_docs else None,
        docs_url="/docs" if serve_docs else None,
        redoc_url="/redoc" if serve_docs else None,
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
        # A JSON API renders nothing, so its responses may load nothing and be
        # framed by no one. HTML (the interactive docs, where enabled) keeps
        # the browser defaults it needs to draw.
        if not response.headers.get("content-type", "").startswith("text/html"):
            response.headers.setdefault(
                "content-security-policy", "default-src 'none'; frame-ancestors 'none'"
            )
        # Only where the deployment is actually served over HTTPS; a local
        # http:// run told to use HTTPS for a year would lock its owner out.
        if settings.noema_secure_cookies:
            response.headers.setdefault(
                "strict-transport-security", "max-age=31536000; includeSubDomains"
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
    v1.include_router(security.router)
    v1.include_router(progression.router)
    v1.include_router(meta.router)
    v1.include_router(demo.router)
    v1.include_router(library.router)
    v1.include_router(sources.router)
    v1.include_router(sources.search_router)
    v1.include_router(concepts.router)
    v1.include_router(study.router)
    v1.include_router(notes_actions.router)
    v1.include_router(imports.router)
    v1.include_router(exports.router)
    v1.include_router(ai.router)
    v1.include_router(journeys.router)
    v1.include_router(tokens.router)
    v1.include_router(feedback.router)
    v1.include_router(focus.router)
    v1.include_router(focus.activity_router)
    v1.include_router(admin.router)
    v1.include_router(billing.router)
    v1.include_router(billing.webhook_router)
    app.include_router(v1)
    app.include_router(health_router)

    return app


health_router = APIRouter(tags=["health"])


@health_router.get("/health")
async def health() -> dict[str, str]:
    """Liveness: the process is up and answering. Touches no dependency, so a
    platform restarting on a failed liveness probe never restarts a healthy
    process because Postgres or Redis blinked. Railway and the Dockerfile
    HEALTHCHECK point here, never at `/health/ready`."""
    return {"status": "ok"}


@health_router.get("/health/ready")
async def ready(request: Request) -> JSONResponse:
    """Readiness reports each dependency separately, with a 503 when any fails.

    A single boolean tells an operator that something is wrong but not what, which is
    the least useful moment to be vague. Redis counts: rate limiting fails open
    without it (noema/core/ratelimit.py), so a deployment that keeps serving with
    no limits at all is exactly what this endpoint exists to surface. Each check
    has a short timeout (noema/core/health.py), and failures name only the
    dependency and the error class.
    """
    redis = getattr(getattr(request.scope.get("app"), "state", None), "redis", None)
    healthy, checks = await readiness(get_engine(), redis)
    settings = get_settings()
    body: dict[str, Any] = {
        **checks,
        "mode": settings.noema_mode.value,
        "default_provider": settings.noema_default_provider,
        "status": "ok" if healthy else "degraded",
    }
    return JSONResponse(body, status_code=200 if healthy else 503)


app = create_app()
