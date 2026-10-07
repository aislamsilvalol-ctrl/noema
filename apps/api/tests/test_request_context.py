"""One request id from the edge to the logs, the AI usage rows and the jobs."""

from __future__ import annotations

import uuid
from typing import Any

import dramatiq
import pytest
import structlog
from dramatiq.brokers.stub import StubBroker
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.request_context import (
    RequestIdMiddleware,
    accept_or_generate,
    current_request_id,
    reset_request_id,
    set_request_id,
)
from noema.db.models import AIUsage, User
from noema.main import app
from noema.providers.base import TaskClass, Usage
from noema.services.usage import UsageWriter


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


@pytest.mark.parametrize(
    "incoming",
    ["req-0123456789", "4f9c2b9e-5d1a-4d43-9a43-8b1d3c0a2f11", "trace:abc.def_123"],
)
def test_a_sane_incoming_id_is_kept(incoming: str) -> None:
    assert accept_or_generate(incoming) == incoming


@pytest.mark.parametrize(
    "incoming",
    [
        None,
        "",
        "short",
        "a" * 129,
        "has space here",
        "line\nbreak-injected",
        "x;rm -rf /",
    ],
)
def test_anything_else_is_replaced_with_a_uuid(incoming: str | None) -> None:
    assert _is_uuid(accept_or_generate(incoming))


def test_the_response_echoes_the_callers_id() -> None:
    response = TestClient(app).get("/health", headers={"x-request-id": "req-0123456789"})
    assert response.headers["x-request-id"] == "req-0123456789"


def test_an_unsafe_id_is_not_echoed() -> None:
    response = TestClient(app).get("/health", headers={"x-request-id": "evil id"})
    assert _is_uuid(response.headers["x-request-id"])


def test_every_response_gets_an_id_without_asking() -> None:
    response = TestClient(app).get("/health")
    assert _is_uuid(response.headers["x-request-id"])


def test_the_id_is_bound_while_the_route_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    async def spy(_engine: Any, _redis: Any) -> tuple[bool, dict[str, str]]:
        seen["var"] = current_request_id()
        seen["log"] = structlog.contextvars.get_contextvars().get("request_id")
        return True, {}

    monkeypatch.setattr("noema.main.readiness", spy)
    TestClient(app).get("/health/ready", headers={"x-request-id": "req-abcdef0123"})

    assert seen == {"var": "req-abcdef0123", "log": "req-abcdef0123"}
    assert current_request_id() is None, "the id must not outlive its request"


async def test_ai_usage_rows_carry_the_request_id(db: AsyncSession, user: User) -> None:
    token = set_request_id("req-usage-0001")
    try:
        await UsageWriter(db, user.id)(
            provider="mock",
            model="mock-1",
            task=TaskClass.TUTOR_CHAT,
            usage=Usage(3, 4),
            succeeded=True,
        )
    finally:
        reset_request_id(token)

    row = await db.scalar(select(AIUsage).where(AIUsage.owner_id == user.id))
    assert row is not None
    assert row.request_id == "req-usage-0001"


def test_a_job_enqueued_from_a_request_runs_under_its_id() -> None:
    broker = StubBroker()
    broker.add_middleware(RequestIdMiddleware())
    seen: dict[str, Any] = {}

    @dramatiq.actor(broker=broker, actor_name="spy_job")
    def spy_job() -> None:
        seen["var"] = current_request_id()
        seen["log"] = structlog.contextvars.get_contextvars().get("request_id")

    token = set_request_id("req-job-000001")
    try:
        message = spy_job.send()
    finally:
        reset_request_id(token)
    assert message.options["request_id"] == "req-job-000001"

    worker = dramatiq.Worker(broker, worker_timeout=50)
    worker.start()
    try:
        broker.join(spy_job.queue_name)
        worker.join()
    finally:
        worker.stop()

    assert seen == {"var": "req-job-000001", "log": "req-job-000001"}


def test_a_job_enqueued_outside_a_request_carries_no_id() -> None:
    broker = StubBroker()
    broker.add_middleware(RequestIdMiddleware())

    @dramatiq.actor(broker=broker, actor_name="cron_job")
    def cron_job() -> None:
        pass

    assert "request_id" not in cron_job.send().options
