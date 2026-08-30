"""AdminIntelligenceService: real aggregation over AIUsage, across every user.

The one property worth pinning precisely here is the one this module's own
docstring calls out: an admin dashboard must see ALL users' spend, not
accidentally inherit the owner_id-scoping every other query in this codebase
correctly applies. Getting that backwards here doesn't leak data (the
opposite direction from this session's usual tenancy bug) -- it silently
under-reports, which is just as dishonest for a cost dashboard.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import AIUsage, User
from noema.services.admin_intelligence import AdminIntelligenceService

pytestmark = pytest.mark.asyncio


def _usage(
    *,
    owner_id: uuid.UUID,
    provider: str = "anthropic",
    model: str = "claude-sonnet-5",
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    cost_cents: float = 10.0,
    succeeded: bool = True,
    created_at: datetime | None = None,
) -> AIUsage:
    return AIUsage(
        owner_id=owner_id,
        provider=provider,
        model=model,
        task="tutor_chat",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_cents=cost_cents,
        succeeded=succeeded,
        created_at=created_at or datetime.now(UTC),
    )


async def test_an_empty_month_reports_real_zeros_not_an_error(
    db: AsyncSession,
) -> None:
    snapshot = await AdminIntelligenceService(db).snapshot()

    assert snapshot.requests_today == 0
    assert snapshot.spend_this_month_cents == 0.0
    assert snapshot.error_rate == 0.0
    assert snapshot.tier_mix == {}
    assert snapshot.top_users == []


async def test_spend_and_tokens_sum_across_every_user_not_just_one(
    db: AsyncSession, user: User, other_user: User
) -> None:
    db.add(_usage(owner_id=user.id, cost_cents=100.0, prompt_tokens=1000))
    db.add(_usage(owner_id=other_user.id, cost_cents=50.0, prompt_tokens=500))
    await db.flush()

    snapshot = await AdminIntelligenceService(db).snapshot()

    assert snapshot.requests_today == 2
    assert snapshot.spend_today_cents == pytest.approx(150.0)
    assert snapshot.tokens_today == 1000 + 50 + 500 + 50  # includes completion_tokens


async def test_top_users_includes_every_owner_ranked_by_spend(
    db: AsyncSession, user: User, other_user: User
) -> None:
    db.add(_usage(owner_id=user.id, cost_cents=500.0))
    db.add(_usage(owner_id=other_user.id, cost_cents=1500.0))
    await db.flush()

    snapshot = await AdminIntelligenceService(db).snapshot()

    assert [u.email for u in snapshot.top_users] == [other_user.email, user.email]
    assert snapshot.top_users[0].spend_cents == pytest.approx(1500.0)


async def test_error_rate_counts_failed_calls_this_month(
    db: AsyncSession, user: User
) -> None:
    db.add(_usage(owner_id=user.id, succeeded=True))
    db.add(_usage(owner_id=user.id, succeeded=True))
    db.add(_usage(owner_id=user.id, succeeded=False))
    await db.flush()

    snapshot = await AdminIntelligenceService(db).snapshot()

    assert snapshot.error_rate == pytest.approx(1 / 3)


async def test_tier_mix_matches_calls_to_the_configured_model(
    db: AsyncSession, user: User
) -> None:
    # Migration 0012 seeds economy -> claude-haiku-4-5-20251001, standard ->
    # claude-sonnet-5, both under provider "anthropic".
    db.add(_usage(owner_id=user.id, model="claude-haiku-4-5-20251001"))
    db.add(_usage(owner_id=user.id, model="claude-haiku-4-5-20251001"))
    db.add(_usage(owner_id=user.id, model="claude-sonnet-5"))
    db.add(_usage(owner_id=user.id, provider="ollama", model="llama3"))  # matches no tier
    await db.flush()

    snapshot = await AdminIntelligenceService(db).snapshot()

    assert snapshot.tier_mix["economy"] == pytest.approx(2 / 4)
    assert snapshot.tier_mix["standard"] == pytest.approx(1 / 4)
    assert "premium" not in snapshot.tier_mix


async def test_a_call_from_last_month_does_not_count_this_month(
    db: AsyncSession, user: User
) -> None:
    # Fixed reference point, not real wall-clock "now" -- a real run on the
    # 1st of a month would put "yesterday" in a different calendar month and
    # make this flaky, the same class of day-boundary bug this session has
    # hit before.
    reference = datetime(2026, 6, 15, tzinfo=UTC)
    last_month = datetime(2026, 5, 31, tzinfo=UTC)
    db.add(_usage(owner_id=user.id, cost_cents=999.0, created_at=last_month))
    await db.flush()

    snapshot = await AdminIntelligenceService(db).snapshot(now=reference)

    assert snapshot.spend_this_month_cents == 0.0
    assert snapshot.top_users == []


async def test_a_call_from_yesterday_counts_this_month_but_not_today(
    db: AsyncSession, user: User
) -> None:
    reference = datetime(2026, 6, 15, tzinfo=UTC)
    yesterday = reference - timedelta(days=1)
    db.add(_usage(owner_id=user.id, cost_cents=42.0, created_at=yesterday))
    await db.flush()

    snapshot = await AdminIntelligenceService(db).snapshot(now=reference)

    assert snapshot.spend_today_cents == 0.0
    assert snapshot.spend_this_month_cents == pytest.approx(42.0)
