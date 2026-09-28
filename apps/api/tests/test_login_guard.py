"""Wrong passwords counted per account, from any address."""

from __future__ import annotations

from typing import Any

import pytest
from redis.exceptions import RedisError

from noema.services.login_guard import (
    MAX_FAILURES,
    RESET_COOLDOWN_SECONDS,
    WINDOW_SECONDS,
    LoginGuard,
    PasswordResetCooldown,
)

pytestmark = pytest.mark.asyncio


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> Any:
        return self.values.get(key)

    async def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    async def expire(self, key: str, seconds: int) -> None:
        self.ttls[key] = seconds

    async def ttl(self, key: str) -> int:
        return self.ttls.get(key, -1)


class DownRedis:
    async def get(self, key: str) -> Any:
        raise RedisError("down")

    async def incr(self, key: str) -> int:
        raise RedisError("down")


async def test_an_account_pauses_after_enough_wrong_passwords() -> None:
    guard = LoginGuard(FakeRedis())
    for _ in range(MAX_FAILURES - 1):
        await guard.failed("Ana@Example.com")
    assert await guard.retry_after("ana@example.com") == 0

    await guard.failed("ana@example.com ")

    assert await guard.retry_after("ANA@example.com") == WINDOW_SECONDS


async def test_one_account_being_attacked_does_not_pause_another() -> None:
    guard = LoginGuard(FakeRedis())
    for _ in range(MAX_FAILURES):
        await guard.failed("victim@example.com")

    assert await guard.retry_after("someone-else@example.com") == 0


async def test_redis_down_counts_nothing_and_locks_no_one() -> None:
    guard = LoginGuard(DownRedis())
    await guard.failed("ana@example.com")
    assert await guard.retry_after("ana@example.com") == 0


async def test_without_redis_the_guard_stands_aside() -> None:
    guard = LoginGuard(None)
    await guard.failed("ana@example.com")
    assert await guard.retry_after("ana@example.com") == 0


# ── the password-reset cooldown ───────────────────────────────────────────


class ClaimingRedis(FakeRedis):
    async def set(self, key: str, value: int, *, nx: bool, ex: int) -> bool | None:
        assert nx and ex == RESET_COOLDOWN_SECONDS
        if key in self.values:
            return None
        self.values[key] = value
        return True


class DownOnSetRedis:
    async def set(self, key: str, value: int, *, nx: bool, ex: int) -> bool | None:
        raise RedisError("down")


async def test_one_reset_email_per_address_per_cooldown() -> None:
    cooldown = PasswordResetCooldown(ClaimingRedis())

    assert await cooldown.claim("Ana@Example.com ") is True
    # Same address however it is typed: the key is the normalised email.
    assert await cooldown.claim("ana@example.com") is False
    assert await cooldown.claim("someone-else@example.com") is True


async def test_the_reset_cooldown_fails_open() -> None:
    assert await PasswordResetCooldown(DownOnSetRedis()).claim("ana@example.com")
    assert await PasswordResetCooldown(None).claim("ana@example.com")
