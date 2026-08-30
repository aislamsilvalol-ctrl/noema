"""Admin-only: per-plan cost/revenue, split precisely into what's real and
what's a projection.

There is no Stripe integration yet (deliberately last in this program), so
nobody on a paid plan is actually being billed -- a plan on ``User.plan`` is
an entitlement `noema/api/v1/admin.py`'s ``set_user_plan`` grants, not
evidence of payment. That makes exactly one number here real and everything
downstream of price a projection:

* real: how many users are on each plan, and what those users actually cost
  the platform in AI spend this month (from ``AIUsage`` -- the same source
  ``admin_intelligence.py``/``admin_users.py`` already read, no parallel
  aggregation).
* projection: what revenue *would* exist if every one of those users were
  actually being charged the plan's published ``monthly_price_cents``. Never
  called "revenue" or "profit" outright anywhere this reaches a caller --
  always paired with "if billed" in the field name or the label, the same
  discipline ``economics.py``'s simulator already established for
  ``estimated_mrr_cents``.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import AIUsage, Plan, PlanConfig, User
from noema.services.admin_users import AdminUsersService
from noema.services.entitlements import current_period_start


@dataclass(frozen=True, slots=True)
class PlanReportRow:
    plan: Plan
    user_count: int
    #: Real: this plan's users' actual AI spend this calendar month.
    real_cost_cents: float
    #: A projection, not a fact -- see this module's own docstring.
    projected_revenue_if_billed_cents: int
    projected_margin_if_billed_cents: float


class AdminReportsService:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    async def profit_projection(self) -> list[PlanReportRow]:
        period_start = current_period_start()

        counts: dict[Plan, int] = {}
        for plan, count in (
            await self.db.execute(
                select(User.plan, func.count(User.id))
                .where(User.deleted_at.is_(None))
                .group_by(User.plan)
            )
        ).all():
            counts[plan] = count

        costs: dict[Plan, float] = {}
        for plan, cost in (
            await self.db.execute(
                select(User.plan, func.coalesce(func.sum(AIUsage.cost_cents), 0.0))
                .join(AIUsage, AIUsage.owner_id == User.id)
                .where(User.deleted_at.is_(None), AIUsage.created_at >= period_start)
                .group_by(User.plan)
            )
        ).all():
            costs[plan] = cost

        prices: dict[Plan, int] = {}
        for plan, price in (
            await self.db.execute(select(PlanConfig.plan, PlanConfig.monthly_price_cents))
        ).all():
            prices[plan] = price

        rows = []
        for plan in Plan:
            user_count = counts.get(plan, 0)
            real_cost = float(costs.get(plan, 0.0))
            price = prices.get(plan, 0)
            projected_revenue = user_count * price
            rows.append(
                PlanReportRow(
                    plan=plan,
                    user_count=user_count,
                    real_cost_cents=real_cost,
                    projected_revenue_if_billed_cents=projected_revenue,
                    projected_margin_if_billed_cents=projected_revenue - real_cost,
                )
            )
        return rows

    async def export_users_csv(self) -> str:
        """Every user, one page at a time, until the roster is exhausted --
        an admin export has to cover everyone, not just the first page
        ``AdminUsersService.list_users`` would otherwise cap at.
        """
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "id",
                "email",
                "display_name",
                "plan",
                "created_at",
                "used_units_this_period",
                "limit_units",
            ]
        )

        users_service = AdminUsersService(self.db)
        cursor = None
        while True:
            rows, cursor = await users_service.list_users(limit=200, cursor=cursor)
            for row in rows:
                writer.writerow(
                    [
                        str(row.id),
                        row.email,
                        row.display_name,
                        row.plan.value,
                        _iso(row.created_at),
                        row.used_units_this_period,
                        row.limit_units,
                    ]
                )
            if cursor is None:
                break

        return buffer.getvalue()


def _iso(value: datetime) -> str:
    return value.isoformat()
