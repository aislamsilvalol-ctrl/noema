"""Admin gating and route wiring for /admin/intelligence and /admin/simulator.

``deps.get_admin_user`` is the actual gate -- an allowlisted email, checked
against ``Settings.noema_admin_emails``, cookie-session only. Calling a route
function directly (this repo's standing test convention) bypasses FastAPI's
own dependency resolution, so the gate itself has to be exercised directly
too, not just assumed to run because the route is typed with ``AdminUser``.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from noema.api.v1 import admin, deps
from noema.core.config import Settings
from noema.core.errors import Forbidden
from noema.db.models import ModelTier, User

pytestmark = pytest.mark.asyncio


async def test_a_non_allowlisted_email_is_forbidden(user: User) -> None:
    settings = Settings(noema_admin_emails="someoneelse@example.com")

    with pytest.raises(Forbidden):
        await deps.get_admin_user(user, settings)


async def test_an_allowlisted_email_passes(user: User) -> None:
    settings = Settings(noema_admin_emails=f" {user.email.upper()} , other@example.com")

    result = await deps.get_admin_user(user, settings)

    assert result is user


async def test_an_empty_allowlist_admits_nobody(user: User) -> None:
    settings = Settings(noema_admin_emails="")

    with pytest.raises(Forbidden):
        await deps.get_admin_user(user, settings)


async def test_intelligence_route_returns_a_real_snapshot(
    db: AsyncSession, user: User
) -> None:
    out = await admin.intelligence(user=user, db=db)

    assert out.requests_today == 0
    assert out.top_users == []
    assert "cache_hit_rate" in out.not_yet_tracked


async def test_simulator_route_computes_from_real_tier_pricing(
    db: AsyncSession, user: User
) -> None:
    payload = admin.SimulatorIn(
        subscribers=100,
        messages_per_day=5,
        avg_input_tokens=500,
        avg_output_tokens=500,
        tier_mix={ModelTier.STANDARD: 1.0},
        active_days_per_month=20,
        plan_price_cents=5990,
    )

    out = await admin.simulator(payload, user=user, db=db)

    assert out.gross_revenue_cents == pytest.approx(100 * 5990)
    assert out.estimated_mrr_cents == out.gross_revenue_cents


async def test_simulator_rejects_a_tier_mix_that_does_not_sum_to_one() -> None:
    with pytest.raises(ValidationError, match=r"tier_mix must sum to 1\.0"):
        admin.SimulatorIn(
            subscribers=1,
            messages_per_day=1,
            avg_input_tokens=1,
            avg_output_tokens=1,
            tier_mix={ModelTier.ECONOMY: 0.5, ModelTier.PREMIUM: 0.2},
            active_days_per_month=30,
            plan_price_cents=100,
        )
