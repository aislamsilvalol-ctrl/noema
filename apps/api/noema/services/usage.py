"""Token accounting and the daily budget guard.

BYOK users are spending their own money, so usage is recorded per call and shown per
task class — not aggregated into an opaque total.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import AIUsage
from noema.providers.base import TaskClass, Usage


class UsageWriter:
    """Gateway callback that persists one row per model call."""

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
    ) -> None:
        self.db.add(
            AIUsage(
                owner_id=self.owner_id,
                provider=provider,
                model=model or "unknown",
                task=task.value,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                cost_cents=usage.cost_cents,
                succeeded=succeeded,
            )
        )
        await self.db.flush()


class DailyBudget:
    """Token ceiling per user per rolling 24 hours."""

    def __init__(self, session: AsyncSession, owner_id: uuid.UUID, limit: int) -> None:
        self.db = session
        self.owner_id = owner_id
        self.limit = limit

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
