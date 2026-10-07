"""Liveness and readiness: what each checks, and what it is allowed to say."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from noema.core import health
from noema.core.health import check_migrations, check_redis, code_migration_heads
from noema.main import app


class SlowRedis:
    async def ping(self) -> None:
        await asyncio.sleep(10)


class GoodRedis:
    async def ping(self) -> bool:
        return True


class LeakyRedis:
    async def ping(self) -> None:
        raise ConnectionError("redis://:hunter2@internal-host:6379 refused")


def test_code_heads_are_the_newest_migration_file() -> None:
    versions = Path(health._ALEMBIC_INI).parent / "alembic" / "versions"
    newest = max(p.name.split("_", 1)[0] for p in versions.glob("[0-9]*.py"))
    assert code_migration_heads() == frozenset({newest})


def test_migrations_match_only_at_the_code_head() -> None:
    (head,) = code_migration_heads()
    assert check_migrations(head).ok
    behind = check_migrations("0001")
    assert not behind.ok
    assert "0001" in behind.detail and head in behind.detail
    assert not check_migrations(None).ok


async def test_redis_check_times_out_quickly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health, "CHECK_TIMEOUT_SECONDS", 0.05)
    result = await check_redis(SlowRedis())
    assert not result.ok
    assert result.detail == "error: timeout"


async def test_a_failure_names_the_class_never_the_message() -> None:
    result = await check_redis(LeakyRedis())
    assert result.detail == "error: ConnectionError"
    assert "hunter2" not in result.detail


def test_liveness_touches_no_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(*_: Any, **__: Any) -> None:
        raise AssertionError("liveness must not check dependencies")

    monkeypatch.setattr("noema.main.readiness", explode)
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_is_503_when_a_dependency_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake(_engine: Any, _redis: Any) -> tuple[bool, dict[str, str]]:
        return False, {"database": "ok", "redis": "error: timeout", "migrations": "ok"}

    monkeypatch.setattr("noema.main.readiness", fake)
    response = TestClient(app).get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["redis"] == "error: timeout"


def test_readiness_is_200_when_everything_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake(_engine: Any, _redis: Any) -> tuple[bool, dict[str, str]]:
        return True, {"database": "ok", "redis": "ok", "migrations": "ok"}

    monkeypatch.setattr("noema.main.readiness", fake)
    response = TestClient(app).get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_readiness_against_the_real_database(db: Any) -> None:
    """`db` only to skip without Postgres; readiness opens its own connection."""
    from sqlalchemy.ext.asyncio import create_async_engine

    from noema.core.config import get_settings

    engine = create_async_engine(get_settings().database_url)
    try:
        ready, checks = await health.readiness(engine, GoodRedis())
    finally:
        await engine.dispose()
    assert checks == {"database": "ok", "redis": "ok", "migrations": "ok"}
    assert ready
