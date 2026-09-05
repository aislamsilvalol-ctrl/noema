"""Token accounting and the daily budget guard.

BYOK users are spending their own money, so usage is recorded per call and shown per
task class — not aggregated into an opaque total.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import AIUsage
from noema.providers.base import TaskClass, Usage
from noema.services.pricing import PricingService


class UsageWriter:
    """Gateway callback that persists one row per model call.

    Cost is computed fresh from the current pricing config rather than trusted from
    ``usage.cost_cents`` -- no provider has ever populated that field (it defaults to
    ``0.0`` and stays there), so relying on it would silently record every call as
    free. See ``noema.services.pricing`` for why the calculation lives there instead
    of here or in a provider.
    """

    def __init__(self, session: AsyncSession, owner_id: uuid.UUID) -> None:
        self.db = session
        self.owner_id = owner_id

    async def __call__(
        self,
        *,
        provider: str,
        model: str,
        task: TaskClass,
        usage: Usage,
        succeeded: bool,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        cost_cents = await PricingService(self.db).cost_cents(
            provider=provider,
            model=model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cached_tokens=usage.cached_tokens,
        )
        metadata = metadata or {}
        feature = metadata.get("feature")
        session_id = metadata.get("session_id")
        self.db.add(
            AIUsage(
                owner_id=self.owner_id,
                provider=provider,
                model=model or "unknown",
                task=task.value,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                cached_tokens=usage.cached_tokens,
                cost_cents=cost_cents,
                succeeded=succeeded,
                feature=str(feature)[:50] if feature else None,
                session_id=_uuid(session_id),
            )
        )
        await self.db.flush()


def _uuid(value: Any) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value)
        except ValueError:
            return None
    return None


class DailyBudget:
    """Token ceiling per user per rolling 24 hours.

    Rolling rather than calendar-day: a midnight reset means a budget that is spent
    at 00:05 leaves the user with nothing for a day, and one that resets at midnight
    in the server's timezone is a mystery to everyone else.

    ``reserve`` is the share held back for interactive work — see
    :data:`noema.providers.gateway.INTERACTIVE_TASKS`.
    """

    def __init__(
        self,
        session: AsyncSession,
        owner_id: uuid.UUID,
        limit: int,
        *,
        reserve: float = 0.0,
    ) -> None:
        self.db = session
        self.owner_id = owner_id
        self.limit = limit
        self.reserve = reserve

    @property
    def reserved_tokens(self) -> int:
        return int(self.limit * self.reserve)

    async def remaining_tokens(self) -> int:
        since = datetime.now(UTC) - timedelta(days=1)
        total = await self.db.scalar(
            select(
                func.coalesce(
                    func.sum(AIUsage.prompt_tokens + AIUsage.completion_tokens), 0
                )
            ).where(AIUsage.owner_id == self.owner_id, AIUsage.created_at >= since)
        )
        return max(self.limit - int(total or 0), 0)


async def usage_by_task(
    session: AsyncSession, owner_id: uuid.UUID, days: int = 30
) -> list[tuple[str, str, int, int, float]]:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = await session.execute(
        select(
            AIUsage.task,
            AIUsage.provider,
            func.sum(AIUsage.prompt_tokens),
            func.sum(AIUsage.completion_tokens),
            func.sum(AIUsage.cost_cents),
        )
        .where(AIUsage.owner_id == owner_id, AIUsage.created_at >= since)
        .group_by(AIUsage.task, AIUsage.provider)
        .order_by(AIUsage.task)
    )
    return [
        (task, provider, int(prompt or 0), int(completion or 0), float(cost or 0.0))
        for task, provider, prompt, completion, cost in rows.all()
    ]
