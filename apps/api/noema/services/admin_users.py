"""Admin-only: every user on the platform, their plan, and their current usage.

Same non-scoping discipline as ``admin_intelligence.py`` -- these queries are
deliberately not filtered by ``owner_id``, because an admin listing users is
supposed to see every user. Reuses ``EntitlementsService``'s own token->unit
conversion and calendar-month window rather than a second copy of that math.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.errors import NotFound
from noema.core.logging import get_logger
from noema.db.models import AIUsage, Plan, PlanConfig, User
from noema.services.entitlements import TOKENS_PER_UNIT, current_period_start

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class AdminUserRow:
    id: uuid.UUID
    email: str
    display_name: str
    plan: Plan
    created_at: datetime
    used_units_this_period: int
    limit_units: int


class AdminUsersService:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    async def list_users(
        self,
        *,
        limit: int = 50,
        cursor: uuid.UUID | None = None,
        search: str | None = None,
    ) -> tuple[list[AdminUserRow], uuid.UUID | None]:
        period_start = current_period_start()

        # One grouped query for every user's usage this period, not one query
        # per user -- a page of 50 users must not become 50 round trips.
        usage_subquery = (
            select(
                AIUsage.owner_id.label("owner_id"),
                func.coalesce(
                    func.sum(AIUsage.prompt_tokens + AIUsage.completion_tokens), 0
                ).label("tokens"),
            )
            .where(AIUsage.created_at >= period_start)
            .group_by(AIUsage.owner_id)
            .subquery()
        )

        stmt = (
            select(User, usage_subquery.c.tokens, PlanConfig.monthly_ai_units)
            .outerjoin(usage_subquery, usage_subquery.c.owner_id == User.id)
            .join(PlanConfig, PlanConfig.plan == User.plan)
            .where(User.deleted_at.is_(None))
        )
        if search:
            like = f"%{search.lower()}%"
            stmt = stmt.where(
                func.lower(User.email).like(like)
                | func.lower(User.display_name).like(like)
            )
        if cursor is not None:
            stmt = stmt.where(User.id > cursor)

        stmt = stmt.order_by(User.id).limit(limit + 1)
        rows = (await self.db.execute(stmt)).all()

        next_cursor = rows[limit - 1][0].id if len(rows) > limit else None
        page = rows[:limit]

        return [
            AdminUserRow(
                id=user.id,
                email=user.email,
                display_name=user.display_name,
                plan=user.plan,
                created_at=user.created_at,
                used_units_this_period=int(tokens or 0) // TOKENS_PER_UNIT,
                limit_units=limit_units,
            )
            for user, tokens, limit_units in page
        ], next_cursor

    async def get_user_row(self, target_user_id: uuid.UUID) -> AdminUserRow:
        """A single user, same shape and same usage math as :meth:`list_users`
        -- used after a write (e.g. :meth:`set_plan`) so the response reflects
        the *current* row, not a hand-assembled partial that could drift from
        what a fresh list would show.
        """
        period_start = current_period_start()
        row = (
            await self.db.execute(
                select(
                    User,
                    func.coalesce(
                        func.sum(AIUsage.prompt_tokens + AIUsage.completion_tokens), 0
                    ),
                    PlanConfig.monthly_ai_units,
                )
                .join(PlanConfig, PlanConfig.plan == User.plan)
                .outerjoin(
                    AIUsage,
                    (AIUsage.owner_id == User.id) & (AIUsage.created_at >= period_start),
                )
                .where(User.id == target_user_id, User.deleted_at.is_(None))
                .group_by(User.id, PlanConfig.monthly_ai_units)
            )
        ).one_or_none()
        if row is None:
            raise NotFound("User not found")
        user, tokens, limit_units = row
        return AdminUserRow(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            plan=user.plan,
            created_at=user.created_at,
            used_units_this_period=int(tokens or 0) // TOKENS_PER_UNIT,
            limit_units=limit_units,
        )

    async def set_plan(
        self, *, admin: User, target_user_id: uuid.UUID, plan: Plan
    ) -> AdminUserRow:
        """Change a user's plan directly -- the only write path that exists
        before Stripe (Phase 8) can drive this from a real subscription
        event. Goes through the real ``User.plan`` column, so
        ``EntitlementsService`` sees the change immediately; nothing here
        invents a second, shadow entitlement.
        """
        user = await self.db.get(User, target_user_id)
        if user is None or user.deleted_at is not None:
            raise NotFound("User not found")
        old_plan = user.plan
        user.plan = plan
        await self.db.flush()
        log.info(
            "admin.plan_changed",
            admin_id=str(admin.id),
            admin_email=admin.email,
            target_user_id=str(target_user_id),
            old_plan=old_plan.value,
            new_plan=plan.value,
        )
        return await self.get_user_row(target_user_id)
