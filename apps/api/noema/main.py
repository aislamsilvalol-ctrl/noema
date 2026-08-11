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
from sqlalchemy import text

from noema.api.v1 import ai, auth, library
from noema.core.config import get_settings
from noema.core.errors import register_error_handlers
from noema.core.logging import configure_logging, get_logger
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
    configure_logging(settings.noema_log_level, json_output=settings.noema_env != "development")
    settings.validate_for_production()
    log.info("api.starting", env=settings.noema_env, mode=settings.noema_mode.value)
    yield
    await get_engine().dispose()


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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(request_id=request_id, path=request.url.path)
        started = time.perf_counter()
        try:
            response: Response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        response.headers["x-request-id"] = request_id
        response.headers["server-timing"] = f"app;dur={(time.perf_counter() - started) * 1000:.1f}"
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

    register_error_handlers(app)

    v1 = APIRouter(prefix="/api/v1")
    v1.include_router(auth.router)
    v1.include_router(library.router)
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
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {type(exc).__name__}"
        healthy = False

    settings = get_settings()
    checks["mode"] = settings.noema_mode.value
    checks["default_provider"] = settings.noema_default_provider
    checks["status"] = "ok" if healthy else "degraded"
    return checks


app = create_app()
