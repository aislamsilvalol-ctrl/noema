"""Failed sign-ins, counted per account.

The request limiter counts per caller, which stops one machine guessing fast.
It does not stop a botnet: a thousand addresses, each well under the limit,
all guessing the same account. This counts failures against the account
itself, whatever address they come from.

Only failures count. A lockout that successful sign-ins also fed would let
anyone who knows an address keep its owner out just by trying to log in;
counting failures makes that cost a wrong password per attempt, and the lock
lifts on its own within the hour.

Keys hold a hash of the normalised email, never the address itself. Redis
down means no counting and no lock — the same fail-open choice the request
limiter makes, logged, so an outage in a cache does not lock everyone out.
"""

from __future__ import annotations

import hashlib
from typing import Any

from redis.exceptions import RedisError

from noema.core.logging import get_logger

log = get_logger(__name__)

#: Wrong passwords per account before sign-in pauses for it.
MAX_FAILURES = 20
#: The window the failures are counted in, and the longest a pause lasts.
WINDOW_SECONDS = 60 * 60
#: How long one address waits between password-reset emails.
RESET_COOLDOWN_SECONDS = 5 * 60


def _digest(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()[:32]


def _key(email: str) -> str:
    return f"noema:login-fail:{_digest(email)}"


class PasswordResetCooldown:
    """One reset email per address per five minutes.

    The route answers 204 either way, so a throttled request looks exactly
    like a first one: the cooldown must never become the enumeration oracle
    the always-204 answer exists to prevent. What it stops is a stranger
    turning "forgot password" into a mail cannon aimed at someone's inbox,
    and at this deployment's sending reputation.
    """

    def __init__(self, redis: Any | None) -> None:
        self._redis = redis

    async def claim(self, email: str) -> bool:
        """True when this request may send; False when one went out recently.

        One atomic ``SET NX EX``: two requests in the same instant cannot
        both win. Without Redis, or with it down, every request may send --
        the reset flow keeps working, which matters more than the throttle.
        """
        if self._redis is None:
            return True
        key = f"noema:reset-cooldown:{_digest(email)}"
        try:
            won = await self._redis.set(key, 1, nx=True, ex=RESET_COOLDOWN_SECONDS)
        except RedisError as exc:
            log.warning("reset_cooldown.unavailable", error=str(exc))
            return True
        return bool(won)


class LoginGuard:
    def __init__(self, redis: Any | None) -> None:
        self._redis = redis

    async def retry_after(self, email: str) -> int:
        """Seconds until this account accepts another attempt; zero when it does."""
        if self._redis is None:
            return 0
        key = _key(email)
        try:
            failures = int(await self._redis.get(key) or 0)
            if failures < MAX_FAILURES:
                return 0
            ttl = int(await self._redis.ttl(key))
        except RedisError as exc:
            log.warning("login_guard.unavailable", error=str(exc))
            return 0
        return max(ttl, 1)

    async def failed(self, email: str) -> None:
        if self._redis is None:
            return
        key = _key(email)
        try:
            failures = int(await self._redis.incr(key))
            if failures == 1:
                await self._redis.expire(key, WINDOW_SECONDS)
        except RedisError as exc:
            log.warning("login_guard.unavailable", error=str(exc))
            return
        if failures == MAX_FAILURES:
            # The moment worth an operator's attention: someone is working
            # through passwords for one account.
            log.warning("security.login_locked", account=key.rsplit(":", 1)[-1])
