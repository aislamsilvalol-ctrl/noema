"""Request rate limiting.

The algorithm is GCRA (the leaky bucket as a meter), evaluated inside a Lua script
so the read and the write are one atomic operation. A check-then-set from Python is
not a rate limit: two concurrent requests both read the old state and both pass.

GCRA rather than a fixed window because a fixed window lets a caller spend the whole
budget in the last second of one window and the whole budget in the first second of
the next — twice the stated limit, at the worst possible moment. GCRA smooths that
out and, usefully, knows exactly how long the caller has to wait.

Failures are **open**: if Redis is down, requests are allowed. A self-hosted study
tool that locks its owner out because a cache is restarting has chosen the wrong
failure. The event is logged so it is not silent.
"""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError

from noema.core.logging import get_logger

log = get_logger(__name__)

__all__ = ["Decision", "RateLimiter"]

# GCRA. `tat` ("theoretical arrival time") is when the bucket next has room for a
# request at the sustained rate. Everything is in milliseconds, from Redis's own
# clock, so callers with skewed clocks cannot buy themselves extra quota.
#
# KEYS[1] bucket   ARGV[1] emission interval (ms)   ARGV[2] burst tolerance (ms)
_GCRA = """
local now = redis.call('TIME')
now = tonumber(now[1]) * 1000 + math.floor(tonumber(now[2]) / 1000)

local interval = tonumber(ARGV[1])
local tolerance = tonumber(ARGV[2])
local tat = tonumber(redis.call('GET', KEYS[1]) or now)
if tat < now then tat = now end

local allow_at = tat - tolerance
if now < allow_at then
  -- Refused. The state is untouched: a refused request must not push the next
  -- allowed one further away, or a client that retries hard is punished forever.
  return {0, allow_at - now, tat - now}
end

local new_tat = tat + interval
redis.call('SET', KEYS[1], new_tat, 'PX', math.ceil(tolerance + interval))
return {1, 0, new_tat - now}
"""


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    limit: int
    #: Requests still available in the burst allowance, rounded down.
    remaining: int
    #: Seconds until the allowance is fully replenished.
    reset_after: int
    #: Seconds to wait before retrying. Zero when the request was allowed.
    retry_after: int


class RateLimiter:
    """A limit of ``limit`` requests per ``period`` seconds, per key."""

    def __init__(self, redis: Redis, *, prefix: str = "noema:rl") -> None:
        self._redis = redis
        self._prefix = prefix
        self._script = redis.register_script(_GCRA)

    async def check(self, key: str, *, limit: int, period: int = 60) -> Decision:
        if limit <= 0:
            # Zero means "no limit configured", not "allow nothing". The opposite
            # reading would make an unset environment variable a lockout.
            return Decision(True, limit, 0, 0, 0)

        interval = period * 1000 / limit
        tolerance = period * 1000

        try:
            allowed, retry_ms, reset_ms = await self._script(
                keys=[f"{self._prefix}:{key}"], args=[interval, tolerance]
            )
        except RedisError as exc:
            log.warning("ratelimit.unavailable", error=str(exc))
            return Decision(True, limit, limit, period, 0)

        remaining = max(int((tolerance - float(reset_ms)) / interval), 0)
        return Decision(
            allowed=bool(allowed),
            limit=limit,
            remaining=remaining,
            reset_after=_ceil_seconds(reset_ms),
            retry_after=_ceil_seconds(retry_ms),
        )


def _ceil_seconds(milliseconds: float) -> int:
    """Round up, but never below one second for a nonzero wait.

    ``Retry-After: 0`` invites an immediate retry that is certain to fail again.
    """
    if milliseconds <= 0:
        return 0
    return max(int(-(-float(milliseconds) // 1000)), 1)
