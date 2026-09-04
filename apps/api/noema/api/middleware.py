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
    {
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/refresh",
        "/api/v1/auth/forgot-password",
        "/api/v1/auth/reset-password",
    }
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
            f"{bucket}:{_caller(request, settings.noema_trusted_proxy_hops)}",
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


def client_key(request: Request, trusted_hops: int) -> str:
    """Public name for `_caller`: the same key other per-caller allowances use."""
    return _caller(request, trusted_hops)


def _caller(request: Request, trusted_hops: int) -> str:
    """A stable, non-identifying key for the caller.

    Hashed because rate-limit keys live in Redis with no expiry policy of their own
    and there is no reason for a session token to be sitting in a second datastore.
    """
    session = request.cookies.get(SESSION_COOKIE)
    if session:
        return "s:" + hashlib.sha256(session.encode()).hexdigest()[:32]

    return (
        "i:" + hashlib.sha256(_client_ip(request, trusted_hops).encode()).hexdigest()[:32]
    )


def _client_ip(request: Request, trusted_hops: int) -> str:
    """Who to hold responsible for an unauthenticated request.

    Behind a platform edge, `request.client.host` is the edge rather than the
    caller. Worse, it is not even stable: deployed on Railway, fifteen rapid login
    attempts each landed in a *different* bucket and the limit never bit, because
    the address changes per request across a pool of proxies.

    So the address is read from `X-Forwarded-For`, counting from the right. Each
    proxy appends the address it received the request *from*, so with one proxy in
    front the last entry is the caller, with two it is the second from last, and
    so on. Everything further left was supplied by the caller — a client can send
    its own `X-Forwarded-For` — and believing any of it would let anyone choose
    their own rate-limit bucket.

    Zero hops means no proxy, and the socket address is the caller.
    """
    if trusted_hops <= 0:
        return request.client.host if request.client else "unknown"

    hops = [
        hop.strip()
        for hop in request.headers.get("x-forwarded-for", "").split(",")
        if hop.strip()
    ]
    index = len(hops) - trusted_hops
    if 0 <= index < len(hops):
        return hops[index]

    # Fewer entries than configured hops: the request did not arrive the way this
    # deployment is configured to expect. Falling back to the socket is the safe
    # reading — it cannot be forged, it is just coarse.
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
