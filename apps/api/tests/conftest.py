from __future__ import annotations

import base64
import os
from collections.abc import AsyncIterator
from typing import Any

import pytest

# Settings are read at import time, so the environment has to be set before any
# noema module is imported.
os.environ.setdefault("NOEMA_ENV", "test")
os.environ.setdefault("NOEMA_MASTER_KEY", base64.b64encode(b"0" * 32).decode())
os.environ.setdefault("NOEMA_SESSION_SECRET", base64.b64encode(b"1" * 32).decode())
os.environ.setdefault("NOEMA_DEFAULT_PROVIDER", "mock")

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)

from noema.core.config import Settings, get_settings
from noema.db.models import User
from noema.services.auth import AuthService

#: CI sets this so a missing database fails the run instead of quietly skipping the
#: tests that enforce tenancy. Locally the suite still runs without Postgres, and
#: says which tests it skipped.
REQUIRE_DB = os.environ.get("NOEMA_REQUIRE_DB") == "1"


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    return get_settings()


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    """A session inside a transaction that is rolled back when the test ends.

    Tests share the schema but never share rows, so none of them can leave state
    behind for the next one to trip over. The engine is per-test rather than
    per-session because a session-scoped async fixture would outlive pytest-asyncio's
    per-test event loop.
    """
    engine = create_async_engine(get_settings().database_url)
    try:
        connection = await engine.connect()
    except Exception as exc:
        await engine.dispose()
        if REQUIRE_DB:
            raise RuntimeError(
                f"NOEMA_REQUIRE_DB=1 but the database is unreachable: {exc}"
            ) from exc
        pytest.skip(f"no database available: {type(exc).__name__}")

    transaction = await connection.begin()
    session = AsyncSession(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    try:
        yield session
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


@pytest.fixture
async def redis() -> AsyncIterator[Any]:
    """A Redis connection on a key prefix no other test uses.

    Same rule as the database: required in CI, skipped locally with a reason. A
    rate limiter that is only ever exercised against a mock is not a rate limiter.
    """
    from redis.asyncio import Redis

    client = Redis.from_url(get_settings().redis_url)
    try:
        await client.ping()
    except Exception as exc:
        await client.aclose()
        if REQUIRE_DB:
            raise RuntimeError(
                f"NOEMA_REQUIRE_DB=1 but Redis is unreachable: {exc}"
            ) from exc
        pytest.skip(f"no redis available: {type(exc).__name__}")

    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
async def user(db: AsyncSession, settings: Settings) -> User:
    return await AuthService(db, settings).register(
        "alice@example.com", "correct-horse-battery", "Alice"
    )


@pytest.fixture
async def other_user(db: AsyncSession, settings: Settings) -> User:
    return await AuthService(db, settings).register(
        "mallory@example.com", "correct-horse-battery", "Mallory"
    )
