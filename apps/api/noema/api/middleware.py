"""Rate limiting middleware.

Two buckets, because they defend against different things:

* a general per-caller limit, which stops one client monopolising a small
  self-hosted instance;
* a much tighter limit on the auth endpoints, because those are the ones worth
  guessing at, and 120 login attempts a minute is a credential-stuffing budget.

Callers are identified by session cookie where there is one and by IP otherwise.
The session cookie is the better key: everyone behind one office NAT shares an IP,
and rate limiting them as a single caller punishes the wrong people.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.responses import JSONResponse

from noema.api.v1.deps import SESSION_COOKIE
from noema.core.config import Settings
from noema.core.errors import RateLimited
from noema.core.logging import get_logger
from noema.core.ratelimit import Decision, RateLimiter

log = get_logger(__name__)

__all__ = ["install_rate_limiting"]

#: Liveness and readiness are polled by orchestrators far more often than any human
#: browses, and a throttled health check reads as an outage.
EXEMPT_PREFIXES = ("/health", "/metrics", "/docs", "/openapi.json")

#: Where credentials are presented. Sign-out is deliberately absent: making it hard
#: to end a session is a security bug, not a defence.
AUTH_PATHS = frozenset(
    {"/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/refresh"}
)


def install_rate_limiting(app: object, limiter: RateLimiter, settings: Settings) -> None:
    """Attach the middleware. Called from ``create_app``."""

    async def rate_limit(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        if request.method == "OPTIONS" or path.startswith(EXEMPT_PREFIXES):
            return await call_next(request)

        if path in AUTH_PATHS:
            limit, bucket = settings.noema_auth_rate_limit_per_minute, "auth"
        else:
            limit, bucket = settings.noema_rate_limit_per_minute, "api"

        decision = await limiter.check(
            f"{bucket}:{_caller(request, settings.noema_trust_forwarded_for)}",
            limit=limit,
            period=60,
        )

        if not decision.allowed:
            log.info("ratelimit.rejected", path=path, bucket=bucket)
            return _too_many(request, decision)

        response = await call_next(request)
        _annotate(response, decision)
        return response

    app.middleware("http")(rate_limit)  # type: ignore[attr-defined]


def _caller(request: Request, trust_forwarded_for: bool) -> str:
    """A stable, non-identifying key for the caller.

    Hashed because rate-limit keys live in Redis with no expiry policy of their own
    and there is no reason for a session token to be sitting in a second datastore.
    """
    session = request.cookies.get(SESSION_COOKIE)
    if session:
        return "s:" + hashlib.sha256(session.encode()).hexdigest()[:32]

    return (
        "i:"
        + hashlib.sha256(_client_ip(request, trust_forwarded_for).encode()).hexdigest()[
            :32
        ]
    )


def _client_ip(request: Request, trust_forwarded_for: bool) -> str:
    """Who to hold responsible for an unauthenticated request.

    Behind a platform edge, `request.client.host` is the edge, not the caller —
    and it varies across a pool, so every attempt lands in a different bucket and
    the limit never bites. Deployed behind Railway this made a burst of fifteen
    logins sail through, which is how it was found.

    `X-Forwarded-For` fixes that only where a proxy you control overwrites it. A
    client can send its own, so trusting it by default would let anyone choose
    their own bucket — hence the setting, and hence the leftmost-of-the-last-hop
    read rather than the leftmost overall.
    """
    if trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for", "")
        # The last entry is the one appended by the nearest trusted proxy;
        # everything to its left is caller-supplied and worthless.
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if hops:
            return hops[-1]

    return request.client.host if request.client else "unknown"


def _annotate(response: Response, decision: Decision) -> None:
    # Draft RFC names (`RateLimit-*`), which is what clients and proxies look for.
    response.headers["ratelimit-limit"] = str(decision.limit)
    response.headers["ratelimit-remaining"] = str(decision.remaining)
    response.headers["ratelimit-reset"] = str(decision.reset_after)


def _too_many(request: Request, decision: Decision) -> JSONResponse:
    # Built from the same error class the handlers use, so a 429 from the middleware
    # is indistinguishable in shape from every other problem the API returns.
    error = RateLimited(
        f"Slow down — this is limited to {decision.limit} requests a minute. "
        f"Try again in {decision.retry_after}s.",
        retry_after=decision.retry_after,
    )
    response = JSONResponse(
        status_code=error.status_code,
        content=error.to_problem(request.url.path),
        media_type="application/problem+json",
    )
    _annotate(response, decision)
    response.headers["retry-after"] = str(decision.retry_after)
    return response
