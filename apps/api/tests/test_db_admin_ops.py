"""GET /admin/ops: what it reports, and what it never does."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from starlette.requests import Request

from noema.api.v1 import admin
from noema.core.config import Settings, get_settings
from noema.db.models import AIUsage, User
from noema.providers.base import ProviderError
from noema.providers.circuit import breaker_for
from noema.services import ops

SECRET = "sk-ant-api03-LEAKLEAKLEAK"


class FakeRedis:
    def __init__(self, depth: int = 3, dead: int = 1, broken: bool = False) -> None:
        self.depth, self.dead, self.broken = depth, dead, broken

    async def ping(self) -> bool:
        if self.broken:
            raise ConnectionError("redis://:pw@host refused")
        return True

    async def hlen(self, key: str) -> int:
        if self.broken:
            raise ConnectionError("refused")
        return self.dead if ".DQ." in key else self.depth


def request_with(redis: Any) -> Request:
    app = SimpleNamespace(state=SimpleNamespace(redis=redis))
    return Request(
        {"type": "http", "headers": [], "app": app, "method": "GET", "path": "/"}
    )


async def test_ops_reports_dependencies_providers_queues_and_failures(
    db: AsyncSession, user: User
) -> None:
    db.add_all(
        [
            AIUsage(owner_id=user.id, provider="anthropic", model="m", task="tutor.chat"),
            AIUsage(
                owner_id=user.id,
                provider="anthropic",
                model="m",
                task="tutor.chat",
                succeeded=False,
            ),
        ]
    )
    await db.flush()
    for _ in range(5):
        breaker_for("anthropic").record_failure(
            ProviderError(SECRET, provider="anthropic", retryable=True, status=503)
        )
    settings = Settings(
        noema_default_provider="anthropic",
        anthropic_api_key=SECRET,
        noema_embedding_provider="mock",
    )

    engine = create_async_engine(get_settings().database_url)
    try:
        report = await ops.build_report(
            db, engine=engine, redis=FakeRedis(), settings=settings
        )
    finally:
        await engine.dispose()

    assert report.checks["database"] == "ok"
    assert report.checks["redis"] == "ok"
    assert report.queues == {"default": 3}
    assert report.dead_letters == {"default": 1}
    assert report.ai_calls >= 2 and report.ai_failures >= 1
    assert report.backup_status == "unknown"
    by_name = {p["provider"]: p for p in report.providers}
    assert by_name["anthropic"]["state"] == "open"
    assert by_name["anthropic"]["last_error"] == "http_503"
    assert by_name["anthropic"]["role"] == "default"
    assert by_name["mock"]["state"] == "closed"
    assert SECRET not in repr(report)


async def test_unreadable_redis_is_said_not_guessed(db: AsyncSession) -> None:
    depths, dead = await ops.queue_depths(FakeRedis(broken=True))
    assert depths == {"default": None} and dead == {"default": None}


async def test_the_route_answers_in_the_published_shape(
    db: AsyncSession, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_async_engine(get_settings().database_url)
    monkeypatch.setattr("noema.api.v1.admin.get_engine", lambda: engine)
    try:
        out = await admin.ops(request_with(FakeRedis(broken=True)), user, db, Settings())
    finally:
        await engine.dispose()
    assert out.checks["redis"] == "error: ConnectionError"
    assert not out.ready
    assert "pw@host" not in out.model_dump_json()


async def test_backup_without_credentials_is_unknown() -> None:
    assert await ops.last_backup(Settings()) == (None, "unknown")


def test_the_route_is_admin_only() -> None:
    route = next(r for r in admin.router.routes if getattr(r, "path", "") == "/admin/ops")
    dependencies = {d.call for d in route.dependant.dependencies}  # type: ignore[attr-defined]
    from noema.api.v1 import deps

    assert deps.get_admin_user in dependencies
