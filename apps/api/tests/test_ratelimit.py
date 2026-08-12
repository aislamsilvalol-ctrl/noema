"""The rate limiter, against a real Redis.

Against a fake it would only prove the Lua string is well-formed. The properties
worth asserting — that concurrent callers cannot both slip through, that a refused
request does not push the caller further back, that the clock comes from Redis —
only exist when the script actually runs.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest

from noema.core.ratelimit import RateLimiter

pytestmark = pytest.mark.asyncio


@pytest.fixture
def limiter(redis: Any) -> RateLimiter:
    return RateLimiter(redis, prefix=f"test:rl:{uuid.uuid4().hex[:8]}")


async def test_a_burst_up_to_the_limit_is_allowed(limiter: RateLimiter) -> None:
    """The limit is a limit, not a target the caller has to creep up on."""
    decisions = [await limiter.check("alice", limit=5, period=60) for _ in range(5)]

    assert all(d.allowed for d in decisions)
    assert [d.remaining for d in decisions] == [4, 3, 2, 1, 0]


async def test_the_next_request_is_refused_with_a_usable_retry_after(
    limiter: RateLimiter,
) -> None:
    for _ in range(5):
        await limiter.check("bob", limit=5, period=60)

    refused = await limiter.check("bob", limit=5, period=60)

    assert not refused.allowed
    # 5 per 60s means one slot every 12s. Never zero: `Retry-After: 0` invites an
    # immediate retry that is certain to fail again.
    assert 1 <= refused.retry_after <= 12


async def test_refusing_does_not_extend_the_wait(limiter: RateLimiter) -> None:
    """Hammering a closed door must not bolt it further.

    A limiter that charges for rejected requests punishes clients with aggressive
    retry logic indefinitely, which is how a rate limit becomes an outage.
    """
    for _ in range(5):
        await limiter.check("carol", limit=5, period=60)

    first = await limiter.check("carol", limit=5, period=60)
    for _ in range(20):
        await limiter.check("carol", limit=5, period=60)
    last = await limiter.check("carol", limit=5, period=60)

    assert not first.allowed and not last.allowed
    assert last.retry_after <= first.retry_after


async def test_callers_are_limited_independently(limiter: RateLimiter) -> None:
    for _ in range(5):
        await limiter.check("dave", limit=5, period=60)

    assert (await limiter.check("erin", limit=5, period=60)).allowed


async def test_concurrent_requests_cannot_exceed_the_limit(
    limiter: RateLimiter,
) -> None:
    """The reason the decision lives in a Lua script.

    Read-then-write from Python would let all twenty of these see the same state
    and pass together.
    """
    results = await asyncio.gather(
        *(limiter.check("frank", limit=5, period=60) for _ in range(20))
    )

    assert sum(1 for r in results if r.allowed) == 5


async def test_a_limit_of_zero_means_unlimited(limiter: RateLimiter) -> None:
    """An unset environment variable must not be a lockout."""
    decisions = [await limiter.check("grace", limit=0, period=60) for _ in range(50)]
    assert all(d.allowed for d in decisions)


async def test_it_fails_open_when_redis_is_gone() -> None:
    """A cache restart is not a reason to lock someone out of their own notes."""
    from redis.asyncio import Redis

    # Port 1 is reserved and never listening, so this is a connection error rather
    # than a slow timeout.
    broken = RateLimiter(Redis.from_url("redis://127.0.0.1:1/0"))
    decision = await broken.check("heidi", limit=1, period=60)

    assert decision.allowed
    await broken._redis.aclose()
