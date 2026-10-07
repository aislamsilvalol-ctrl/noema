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


class BreachedPassword(NoemaError):
    """A new password that appears in public breach lists."""

    slug = "breached-password"
    title = "Password found in a breach"


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


class WrongPassword(Forbidden):
    """A step-up confirmation that did not match.

    Its own type so a client tells it apart from a CSRF refusal, which is also
    a 403 but means something else entirely.
    """

    slug = "wrong-password"
    title = "Wrong password"


class EmailNotVerified(Forbidden):
    """An AI route on a deployment that requires a confirmed address.

    Its own type so a client shows "confirm your email" with a resend
    button, not the generic forbidden it would show for a CSRF failure.
    """

    slug = "email-not-verified"
    title = "Email not verified"


class LinkExpired(Unauthorized):
    """A one-time link presented after its time, as opposed to one that
    never existed. The distinction leaks nothing (a 256-bit token cannot be
    guessed into existence) and lets a page say "expired, here is a new one"
    instead of "invalid"."""

    slug = "link-expired"
    title = "Link expired"


class Conflict(NoemaError):
    status_code = status.HTTP_409_CONFLICT
    slug = "conflict"
    title = "Conflict"


class RateLimited(NoemaError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    slug = "rate-limited"
    title = "Too many requests"


class QuotaExceeded(NoemaError):
    status_code = status.HTTP_413_CONTENT_TOO_LARGE
    slug = "quota-exceeded"
    title = "Quota exceeded"


class PlanLimitReached(NoemaError):
    """The month's AI Compute Units on this plan are spent.

    402, not 429: waiting does not help, a bigger plan does. Carries
    ``used_units`` and ``limit_units`` so a client can say exactly that.
    """

    status_code = status.HTTP_402_PAYMENT_REQUIRED
    slug = "plan-limit-reached"
    title = "Plan limit reached"


class ProviderUnavailable(NoemaError):
    status_code = status.HTTP_502_BAD_GATEWAY
    slug = "provider-unavailable"
    title = "AI provider unavailable"


class AITimeout(ProviderUnavailable):
    """The AI provider did not answer in time. 504, so a client can tell
    "slow, try again" from "failing"."""

    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    slug = "ai-timeout"
    title = "AI provider timed out"


#: What a learner reads when a model call fails. Provider text never reaches a
#: client: it can name the deployment's billing state, its account or its key.
AI_UNAVAILABLE = "The AI provider is unavailable right now. Try again in a moment."
AI_TIMED_OUT = "The AI provider took too long to answer. Try again in a moment."


def ai_problem(exc: BaseException, lead: str | None = None) -> ProviderUnavailable:
    """The client-safe problem for a failed model call.

    ``lead`` says what could not happen ("The explanation could not be
    evaluated."); the rest is a fixed sentence, never ``str(exc)``.
    """
    timed_out = isinstance(exc, TimeoutError) or bool(getattr(exc, "timed_out", False))
    sentence = AI_TIMED_OUT if timed_out else AI_UNAVAILABLE
    detail = f"{lead} {sentence}" if lead else sentence
    retryable = bool(getattr(exc, "retryable", timed_out))
    if timed_out:
        return AITimeout(detail, retryable=True)
    return ProviderUnavailable(detail, retryable=retryable)


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

    # A ProviderError that escaped its route would otherwise be a bare 500,
    # and its text (the upstream's own words) must not reach the client anyway.
    from noema.providers.base import ProviderError

    @app.exception_handler(ProviderError)
    async def _handle_provider_error(
        request: Request, exc: ProviderError
    ) -> JSONResponse:
        problem = ai_problem(exc)
        return JSONResponse(
            status_code=problem.status_code,
            content=problem.to_problem(str(request.url.path)),
            media_type="application/problem+json",
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
