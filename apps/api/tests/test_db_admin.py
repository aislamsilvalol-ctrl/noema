"""Admin gating and route wiring for /admin/intelligence and /admin/simulator.

``deps.get_admin_user`` is the actual gate -- an allowlisted email, checked
against ``Settings.noema_admin_emails``, cookie-session only. Calling a route
function directly (this repo's standing test convention) bypasses FastAPI's
own dependency resolution, so the gate itself has to be exercised directly
too, not just assumed to run because the route is typed with ``AdminUser``.
"""

from __future__ import annotations

import os
import time

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from noema.api.v1 import admin, deps
from noema.core import totp
from noema.core.config import Settings
from noema.core.crypto import SecretBox
from noema.core.errors import Forbidden
from noema.db.models import ModelTier, User
from noema.services.mfa import MfaService

pytestmark = pytest.mark.asyncio


async def with_authenticator(db: AsyncSession, user: User) -> None:
    """Two-step verification switched on the way a person does it."""
    mfa = MfaService(db, SecretBox(os.urandom(32)))
    setup = await mfa.begin(user)
    await mfa.confirm(user, totp.code_at(setup.secret, time.time()))


async def test_a_non_allowlisted_email_is_forbidden(db: AsyncSession, user: User) -> None:
    settings = Settings(noema_admin_emails="someoneelse@example.com")

    with pytest.raises(Forbidden):
        await deps.get_admin_user(user, db, settings)


async def test_an_allowlisted_email_with_two_step_verification_passes(
    db: AsyncSession, user: User
) -> None:
    settings = Settings(noema_admin_emails=f" {user.email.upper()} , other@example.com")
    await with_authenticator(db, user)

    result = await deps.get_admin_user(user, db, settings)

    assert result is user


async def test_an_allowlisted_email_without_two_step_verification_is_turned_away(
    db: AsyncSession, user: User
) -> None:
    """A password alone does not open the business's numbers."""
    settings = Settings(noema_admin_emails=user.email)

    with pytest.raises(Forbidden, match="two-step"):
        await deps.get_admin_user(user, db, settings)


async def test_an_empty_allowlist_admits_nobody(db: AsyncSession, user: User) -> None:
    settings = Settings(noema_admin_emails="")

    with pytest.raises(Forbidden):
        await deps.get_admin_user(user, db, settings)


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
