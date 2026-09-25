"""Wrong passwords counted per account, from any address."""

from __future__ import annotations

from typing import Any

import pytest
from redis.exceptions import RedisError

from noema.services.login_guard import MAX_FAILURES, WINDOW_SECONDS, LoginGuard

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
