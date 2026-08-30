"""Real-data admin dashboard queries over ``AIUsage``.

Everything here is a read of what actually happened -- no projections, no
what-if numbers (those live in ``noema/services/economics.py``). An admin
views every user's data by design: this module's queries are deliberately
*not* scoped by ``owner_id`` the way almost every other query in this
codebase is, because an admin dashboard that accidentally inherited a
per-user scope would silently under-report rather than leak -- a different
failure shape than this session's usual tenancy bug, but just as wrong.

Two real metrics the product spec also asks for -- cache-hit-rate and RAG
call counts -- are not built here. ``noema/providers/cache.py``'s
``EmbeddingCache`` logs hits/misses to structured logs only
(``log.info("embeddings.cache", ...)``); nothing persists them anywhere
queryable. Reporting a number for either would mean fabricating one. Real
instrumentation for those is separate, honest future scope.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import AIUsage, ModelTierConfig, User


def today_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


@dataclass(frozen=True, slots=True)
class TopUser:
    user_id: uuid.UUID
    email: str
    spend_cents: float


@dataclass(frozen=True, slots=True)
class IntelligenceSnapshot:
    requests_today: int
    tokens_today: int
    spend_today_cents: float
    spend_this_month_cents: float
    #: Fraction of this-month calls that failed (``AIUsage.succeeded is False``).
    error_rate: float
    #: Tier name -> fraction of this-month calls whose (provider, model)
    #: matches that tier's currently-configured model. A call made under a
    #: tier's *previous* model, before an admin changed it, is invisible to
    #: this mix on purpose -- it reports what the current configuration
    #: would produce, not a historical reconstruction.
    tier_mix: dict[str, float]
    top_users: list[TopUser]


class AdminIntelligenceService:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    async def snapshot(
        self, *, top_n: int = 10, now: datetime | None = None
    ) -> IntelligenceSnapshot:
        today = today_start(now)
        month = month_start(now)

        requests_today, tokens_today, spend_today_cents = (
            await self.db.execute(
                select(
                    func.count(AIUsage.id),
                    func.coalesce(
                        func.sum(AIUsage.prompt_tokens + AIUsage.completion_tokens), 0
                    ),
                    func.coalesce(func.sum(AIUsage.cost_cents), 0.0),
                ).where(AIUsage.created_at >= today)
            )
        ).one()

        spend_this_month_cents = await self.db.scalar(
            select(func.coalesce(func.sum(AIUsage.cost_cents), 0.0)).where(
                AIUsage.created_at >= month
            )
        )

        calls_this_month, failed_this_month = (
            await self.db.execute(
                select(
                    func.count(AIUsage.id),
                    func.coalesce(
                        func.sum(case((AIUsage.succeeded.is_(False), 1), else_=0)), 0
                    ),
                ).where(AIUsage.created_at >= month)
            )
        ).one()
        error_rate = (failed_this_month / calls_this_month) if calls_this_month else 0.0

        tier_mix = await self._tier_mix(month, calls_this_month)
        top_users = await self._top_users(month, top_n)

        return IntelligenceSnapshot(
            requests_today=int(requests_today),
            tokens_today=int(tokens_today),
            spend_today_cents=float(spend_today_cents),
            spend_this_month_cents=float(spend_this_month_cents or 0.0),
            error_rate=error_rate,
            tier_mix=tier_mix,
            top_users=top_users,
        )

    async def _tier_mix(self, month: datetime, total_calls: int) -> dict[str, float]:
        if not total_calls:
            return {}
        rows = (
            await self.db.execute(
                select(ModelTierConfig.tier, func.count(AIUsage.id))
                .join(
                    ModelTierConfig,
                    (ModelTierConfig.provider == AIUsage.provider)
                    & (ModelTierConfig.model == AIUsage.model),
                )
                .where(AIUsage.created_at >= month)
                .group_by(ModelTierConfig.tier)
            )
        ).all()
        return {tier.value: count / total_calls for tier, count in rows}

    async def _top_users(self, month: datetime, top_n: int) -> list[TopUser]:
        rows = (
            await self.db.execute(
                select(User.id, User.email, func.sum(AIUsage.cost_cents))
                .join(User, User.id == AIUsage.owner_id)
                .where(AIUsage.created_at >= month)
                .group_by(User.id, User.email)
                .order_by(func.sum(AIUsage.cost_cents).desc())
                .limit(top_n)
            )
        ).all()
        return [
            TopUser(user_id=user_id, email=email, spend_cents=float(spend or 0.0))
            for user_id, email, spend in rows
        ]
