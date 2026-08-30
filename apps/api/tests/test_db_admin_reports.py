"""AdminReportsService: the profit *projection* and the users CSV export.

The whole point of this module is the line between real and projected --
there is no Stripe integration yet, so ``User.plan`` is an entitlement, not
evidence anyone is actually paying. ``real_cost_cents`` must come from real
``AIUsage`` rows; ``projected_revenue_if_billed_cents`` must never be
confused for it, in the code or in a test's own naming.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from noema.api.v1 import admin
from noema.db.models import AIUsage, Plan, User
from noema.services.admin_reports import AdminReportsService
from noema.services.admin_users import AdminUsersService
from noema.services.entitlements import current_period_start

pytestmark = pytest.mark.asyncio


def _usage(
    *, owner_id: uuid.UUID, cost_cents: float, created_at: datetime | None = None
) -> AIUsage:
    return AIUsage(
        owner_id=owner_id,
        provider="anthropic",
        model="claude-sonnet-5",
        task="tutor_chat",
        prompt_tokens=1_000,
        completion_tokens=200,
        cost_cents=cost_cents,
        succeeded=True,
        created_at=created_at or datetime.now(UTC),
    )


async def test_counts_every_user_on_their_actual_plan(
    db: AsyncSession, user: User, other_user: User
) -> None:
    await AdminUsersService(db).set_plan(
        admin=user, target_user_id=other_user.id, plan=Plan.PRO
    )

    rows = await AdminReportsService(db).profit_projection()

    by_plan = {r.plan: r for r in rows}
    assert by_plan[Plan.FREE].user_count >= 1  # user themselves, still free
    assert by_plan[Plan.PRO].user_count == 1


async def test_real_cost_is_summed_from_ai_usage_not_guessed(
    db: AsyncSession, user: User, other_user: User
) -> None:
    await AdminUsersService(db).set_plan(
        admin=user, target_user_id=other_user.id, plan=Plan.PRO
    )
    db.add(_usage(owner_id=other_user.id, cost_cents=150.0))
    db.add(_usage(owner_id=other_user.id, cost_cents=50.0))
    await db.flush()

    rows = await AdminReportsService(db).profit_projection()

    pro = next(r for r in rows if r.plan == Plan.PRO)
    assert pro.real_cost_cents == 200.0


async def test_usage_from_a_prior_billing_period_does_not_count(
    db: AsyncSession, user: User, other_user: User
) -> None:
    await AdminUsersService(db).set_plan(
        admin=user, target_user_id=other_user.id, plan=Plan.PRO
    )
    stale = current_period_start() - timedelta(days=1)
    db.add(_usage(owner_id=other_user.id, cost_cents=999.0, created_at=stale))
    await db.flush()

    rows = await AdminReportsService(db).profit_projection()

    pro = next(r for r in rows if r.plan == Plan.PRO)
    assert pro.real_cost_cents == 0.0


async def test_projected_revenue_is_user_count_times_the_published_price(
    db: AsyncSession, user: User, other_user: User
) -> None:
    await AdminUsersService(db).set_plan(
        admin=user, target_user_id=other_user.id, plan=Plan.PRO
    )

    rows = await AdminReportsService(db).profit_projection()

    pro = next(r for r in rows if r.plan == Plan.PRO)
    # PlanConfig seeds Pro at R$59,90 = 5_990 cents (migration 0014).
    assert pro.projected_revenue_if_billed_cents == 5_990


async def test_projected_margin_is_revenue_minus_real_cost(
    db: AsyncSession, user: User, other_user: User
) -> None:
    await AdminUsersService(db).set_plan(
        admin=user, target_user_id=other_user.id, plan=Plan.PRO
    )
    db.add(_usage(owner_id=other_user.id, cost_cents=90.0))
    await db.flush()

    rows = await AdminReportsService(db).profit_projection()

    pro = next(r for r in rows if r.plan == Plan.PRO)
    assert pro.projected_margin_if_billed_cents == 5_990 - 90.0


async def test_free_plan_never_shows_projected_revenue(
    db: AsyncSession, user: User
) -> None:
    rows = await AdminReportsService(db).profit_projection()

    free = next(r for r in rows if r.plan == Plan.FREE)
    assert free.projected_revenue_if_billed_cents == 0


async def test_csv_export_contains_every_registered_user(
    db: AsyncSession, user: User, other_user: User
) -> None:
    csv_data = await AdminReportsService(db).export_users_csv()

    reader = csv.DictReader(io.StringIO(csv_data))
    rows = list(reader)
    emails = {r["email"] for r in rows}
    assert user.email in emails
    assert other_user.email in emails


async def test_csv_export_reflects_real_usage_and_plan(
    db: AsyncSession, user: User, other_user: User
) -> None:
    await AdminUsersService(db).set_plan(
        admin=user, target_user_id=other_user.id, plan=Plan.MAX
    )
    db.add(_usage(owner_id=other_user.id, cost_cents=10.0))
    await db.flush()

    csv_data = await AdminReportsService(db).export_users_csv()

    reader = csv.DictReader(io.StringIO(csv_data))
    row = next(r for r in reader if r["email"] == other_user.email)
    assert row["plan"] == "max"
    assert int(row["used_units_this_period"]) == 1


async def test_profit_report_route_returns_every_plan(
    db: AsyncSession, user: User
) -> None:
    out = await admin.profit_report(user=user, db=db)

    plans = {row.plan for row in out}
    assert plans == set(Plan)


async def test_export_users_report_route_returns_a_downloadable_csv(
    db: AsyncSession, user: User
) -> None:
    response = await admin.export_users_report(user=user, db=db)

    assert response.media_type == "text/csv"
    assert "attachment" in response.headers["content-disposition"]
    body = (
        response.body.decode() if isinstance(response.body, bytes) else str(response.body)
    )
    assert user.email in body
