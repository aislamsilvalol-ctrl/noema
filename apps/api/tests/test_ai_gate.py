"""The allowances every AI route inherits by taking `GatewayDep`.

Two of them, checked in `deps._gateway` before a provider is built: a
per-learner call limit in Redis, and the plan's monthly AI allowance. The
plan check used to live in the Professor route alone; the other nine
AI-spending routes let a blocked learner keep spending.

No database here: the entitlement service is replaced with a scripted one
and Redis with a fake that answers the GCRA script directly.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from redis.exceptions import RedisError
from starlette.requests import Request

from noema.api.v1 import deps
from noema.core.config import Settings
from noema.core.crypto import SecretBox
from noema.core.errors import PlanLimitReached, ProviderUnavailable, RateLimited
from noema.providers.base import ProviderError
from noema.services.entitlements import EntitlementCheck

pytestmark = pytest.mark.asyncio

USER = SimpleNamespace(id=uuid.uuid4())


class ScriptedRedis:
    """Answers the rate-limit Lua script with a fixed verdict."""

    def __init__(self, verdict: list[int] | Exception) -> None:
        self.verdict = verdict
        self.keys: list[str] = []

    def register_script(self, _script: str) -> Callable[..., Any]:
        async def run(*, keys: list[str], args: list[float]) -> list[int]:
            self.keys.extend(keys)
            if isinstance(self.verdict, Exception):
                raise self.verdict
            return self.verdict

        return run


def _request(redis: object | None) -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/cards/generate",
        "query_string": b"",
        "headers": [],
    }
    if redis is not None:
        scope["app"] = SimpleNamespace(state=SimpleNamespace(redis=redis))
    return Request(scope)


def _blocked_plan(monkeypatch: pytest.MonkeyPatch, *, allowed: bool) -> None:
    class Scripted:
        def __init__(self, db: Any, user: Any) -> None:
            pass

        async def check_ai_usage(self) -> EntitlementCheck:
            return EntitlementCheck(
                allowed=allowed, warn=False, used_units=50, limit_units=50
            )

    monkeypatch.setattr(deps, "EntitlementsService", Scripted)


# ── the per-learner call limit ────────────────────────────────────────────


async def test_a_refused_call_is_a_429_with_a_retry_after() -> None:
    redis = ScriptedRedis([0, 7000, 12000])
    settings = Settings(noema_ai_calls_per_minute=30)

    with pytest.raises(RateLimited) as caught:
        await deps.enforce_ai_call_limit(_request(redis), USER.id, settings)

    assert caught.value.extra["retry_after"] == 7
    # Keyed on the account, so three tabs or three cookies share one allowance.
    assert redis.keys == [f"noema:ai:u:{USER.id}"]


async def test_an_allowed_call_passes() -> None:
    settings = Settings(noema_ai_calls_per_minute=30)

    await deps.enforce_ai_call_limit(
        _request(ScriptedRedis([1, 0, 2000])), USER.id, settings
    )


async def test_redis_down_lets_the_call_through() -> None:
    settings = Settings(noema_ai_calls_per_minute=30)

    await deps.enforce_ai_call_limit(
        _request(ScriptedRedis(RedisError("down"))), USER.id, settings
    )


async def test_no_redis_and_a_zero_limit_both_mean_no_counting() -> None:
    await deps.enforce_ai_call_limit(
        _request(None), USER.id, Settings(noema_ai_calls_per_minute=30)
    )
    await deps.enforce_ai_call_limit(
        _request(ScriptedRedis([0, 7000, 12000])),
        USER.id,
        Settings(noema_ai_calls_per_minute=0),
    )


# ── the plan gate ──────────────────────────────────────────────────────────


async def test_a_learner_over_the_plan_limit_gets_no_gateway(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The response a non-streaming route sends: 402, a stable slug, and the
    numbers the Professor's `blocked` event carries, so a client can say the
    same thing either way."""
    _blocked_plan(monkeypatch, allowed=False)

    with pytest.raises(PlanLimitReached) as caught:
        await deps.get_gateway(
            request=_request(None),
            user=USER,  # type: ignore[arg-type]
            db=None,  # type: ignore[arg-type]
            settings=settings,
            box=SecretBox.from_base64(settings.noema_master_key),
            router=deps.get_router(settings),
        )

    problem = caught.value.to_problem("/api/v1/cards/generate")
    assert problem["status"] == 402
    assert problem["type"].endswith("/plan-limit-reached")
    assert (problem["used_units"], problem["limit_units"]) == (50, 50)


async def test_the_professors_gateway_leaves_the_plan_check_to_the_route(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`/ai/professor` answers a blocked learner inside its stream, so its
    dependency must not refuse first. Proven by getting *past* the gate to
    the provider, which is scripted to fail."""
    _blocked_plan(monkeypatch, allowed=False)

    async def no_provider(name: str, settings_: Settings, credentials: Any) -> None:
        raise ProviderError("no key", provider=name)

    monkeypatch.setattr(deps, "build_provider", no_provider)

    with pytest.raises(ProviderUnavailable):
        await deps.get_self_gated_stream_gateway(
            request=_request(None),
            user=USER,  # type: ignore[arg-type]
            db=None,  # type: ignore[arg-type]
            settings=settings,
            box=SecretBox.from_base64(settings.noema_master_key),
            router=deps.get_router(settings),
        )


async def test_the_call_limit_is_checked_before_the_plan(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Redis before the usage query: a hammering caller should never make
    the database sum a month of usage rows per attempt."""
    _blocked_plan(monkeypatch, allowed=False)
    limited = Settings(noema_ai_calls_per_minute=30)

    with pytest.raises(RateLimited):
        await deps.get_gateway(
            request=_request(ScriptedRedis([0, 1000, 2000])),
            user=USER,  # type: ignore[arg-type]
            db=None,  # type: ignore[arg-type]
            settings=limited,
            box=SecretBox.from_base64(settings.noema_master_key),
            router=deps.get_router(settings),
        )
