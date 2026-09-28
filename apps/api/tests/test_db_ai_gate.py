"""The plan gate in `get_gateway`, against the real entitlement query."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from noema.api.v1 import deps
from noema.core.config import Settings
from noema.core.crypto import SecretBox
from noema.core.errors import PlanLimitReached
from noema.db.models import AIUsage, Plan, PlanConfig, User
from noema.providers.gateway import AIGateway
from noema.services.entitlements import TOKENS_PER_UNIT

pytestmark = pytest.mark.asyncio


def _request() -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/cards/generate",
        "query_string": b"",
        "headers": [],
    }
    return Request(scope)


async def _gateway_for(db: AsyncSession, user: User, settings: Settings) -> AIGateway:
    return await deps.get_gateway(
        request=_request(),
        user=user,
        db=db,
        settings=settings,
        box=SecretBox.from_base64(settings.noema_master_key),
        router=deps.get_router(settings),
    )


async def test_a_learner_at_the_plan_limit_is_refused_before_any_provider(
    db: AsyncSession, user: User, settings: Settings
) -> None:
    free = await db.get(PlanConfig, Plan.FREE)
    assert free is not None
    db.add(
        AIUsage(
            owner_id=user.id,
            provider="anthropic",
            model="claude-sonnet-5",
            task="tutor_chat",
            prompt_tokens=free.monthly_ai_units * TOKENS_PER_UNIT,
            completion_tokens=0,
            created_at=datetime.now(UTC),
        )
    )
    await db.flush()

    with pytest.raises(PlanLimitReached) as caught:
        await _gateway_for(db, user, settings)

    assert caught.value.extra["limit_units"] == free.monthly_ai_units
    assert caught.value.extra["used_units"] >= free.monthly_ai_units


async def test_a_learner_with_allowance_left_gets_a_gateway(
    db: AsyncSession, user: User, settings: Settings
) -> None:
    gateway = await _gateway_for(db, user, settings)

    assert isinstance(gateway, AIGateway)
