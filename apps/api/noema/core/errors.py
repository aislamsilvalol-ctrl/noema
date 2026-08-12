"""RFC 9457 problem details.

Errors are part of the API contract, so they get the same care as success responses:
a stable machine-readable ``type``, a human ``detail``, and never an internal trace.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

BASE_TYPE_URI = "https://noema.dev/errors/"


class NoemaError(Exception):
    """Base application error. Subclasses declare their own status and slug."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    slug: str = "bad-request"
    title: str = "Bad request"

    def __init__(self, detail: str, **extra: Any) -> None:
        super().__init__(detail)
        self.detail = detail
        self.extra = extra

    def to_problem(self, instance: str) -> dict[str, Any]:
        return {
            "type": f"{BASE_TYPE_URI}{self.slug}",
            "title": self.title,
            "status": self.status_code,
            "detail": self.detail,
            "instance": instance,
            **self.extra,
        }


class NotFound(NoemaError):
    status_code = status.HTTP_404_NOT_FOUND
    slug = "not-found"
    title = "Not found"


class Unauthorized(NoemaError):
    status_code = status.HTTP_401_UNAUTHORIZED
    slug = "unauthorized"
    title = "Authentication required"


class Forbidden(NoemaError):
    status_code = status.HTTP_403_FORBIDDEN
    slug = "forbidden"
    title = "Forbidden"


class Conflict(NoemaError):
    status_code = status.HTTP_409_CONFLICT
    slug = "conflict"
    title = "Conflict"


class RateLimited(NoemaError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    slug = "rate-limited"
    title = "Too many requests"


class QuotaExceeded(NoemaError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    slug = "quota-exceeded"
    title = "Quota exceeded"


class ProviderUnavailable(NoemaError):
    status_code = status.HTTP_502_BAD_GATEWAY
    slug = "provider-unavailable"
    title = "AI provider unavailable"


class FeatureUnavailable(NoemaError):
    """A feature disabled by deployment mode — local mode, signups off, etc."""

    status_code = status.HTTP_403_FORBIDDEN
    slug = "feature-unavailable"
    title = "Feature unavailable in this deployment"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(NoemaError)
    async def _handle_noema_error(request: Request, exc: NoemaError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_problem(str(request.url.path)),
            media_type="application/problem+json",
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "type": f"{BASE_TYPE_URI}validation-failed",
                "title": "Validation failed",
                "status": 422,
                "detail": "One or more fields are invalid.",
                "instance": str(request.url.path),
                "errors": [
                    {"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]}
                    for e in exc.errors()
                ],
            },
            media_type="application/problem+json",
        )
