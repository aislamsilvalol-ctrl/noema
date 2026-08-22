"""Token accounting and the daily budget guard, against a real database.

The budget guard is the one thing standing between a BYOK user and a runaway
call loop spending their own money, and it had no tests at all — worth
verifying the rolling window, the clamp to zero, and tenancy actually hold.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import AIUsage, User
from noema.providers.base import TaskClass, Usage
from noema.services.usage import DailyBudget, UsageWriter, usage_by_task

pytestmark = pytest.mark.asyncio


async def add_usage(
    db: AsyncSession,
    owner_id: uuid.UUID,
    *,
    provider: str = "anthropic",
    model: str = "claude",
    task: str = "tutor.chat",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost_cents: float = 0.0,
    created_at: datetime | None = None,
) -> AIUsage:
    row = AIUsage(
        owner_id=owner_id,
        provider=provider,
        model=model,
        task=task,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_cents=cost_cents,
    )
    if created_at is not None:
        row.created_at = created_at
    db.add(row)
    await db.flush()
    return row


# ---------------------------------------------------------------------------
# UsageWriter
# ---------------------------------------------------------------------------


async def test_usage_writer_persists_a_row(db: AsyncSession, user: User) -> None:
    writer = UsageWriter(db, user.id)

    await writer(
        provider="anthropic",
        model="claude-5",
        task=TaskClass.TUTOR_CHAT,
        usage=Usage(prompt_tokens=100, completion_tokens=50, cost_cents=1.5),
        succeeded=True,
    )

    row = await db.scalar(select(AIUsage).where(AIUsage.owner_id == user.id))
    assert row is not None
    assert row.provider == "anthropic"
    assert row.model == "claude-5"
    assert row.task == "tutor.chat"
    assert row.prompt_tokens == 100
    assert row.completion_tokens == 50
    assert row.cost_cents == 1.5
    assert row.succeeded is True


async def test_usage_writer_records_a_failed_call(db: AsyncSession, user: User) -> None:
    writer = UsageWriter(db, user.id)

    await writer(
        provider="anthropic",
        model="claude-5",
        task=TaskClass.TUTOR_CHAT,
        usage=Usage(),
        succeeded=False,
    )

    row = await db.scalar(select(AIUsage).where(AIUsage.owner_id == user.id))
    assert row is not None
    assert row.succeeded is False


async def test_usage_writer_falls_back_to_unknown_for_an_empty_model(
    db: AsyncSession, user: User
) -> None:
    writer = UsageWriter(db, user.id)

    await writer(
        provider="ollama",
        model="",
        task=TaskClass.EMBED,
        usage=Usage(),
        succeeded=True,
    )

    row = await db.scalar(select(AIUsage).where(AIUsage.owner_id == user.id))
    assert row is not None
    assert row.model == "unknown"


# ---------------------------------------------------------------------------
# DailyBudget
# ---------------------------------------------------------------------------


async def test_reserved_tokens_is_the_limit_times_the_reserve_share(
    db: AsyncSession,
) -> None:
    budget = DailyBudget(db, uuid.uuid4(), 1000, reserve=0.2)

    assert budget.reserved_tokens == 200


async def test_remaining_tokens_is_the_full_limit_with_no_usage(
    db: AsyncSession, user: User
) -> None:
    budget = DailyBudget(db, user.id, 1000)

    assert await budget.remaining_tokens() == 1000


async def test_remaining_tokens_subtracts_recent_usage(
    db: AsyncSession, user: User
) -> None:
    await add_usage(db, user.id, prompt_tokens=100, completion_tokens=50)
    budget = DailyBudget(db, user.id, 1000)

    assert await budget.remaining_tokens() == 850


async def test_remaining_tokens_ignores_usage_older_than_24_hours(
    db: AsyncSession, user: User
) -> None:
    stale = datetime.now(UTC) - timedelta(days=1, minutes=1)
    await add_usage(db, user.id, prompt_tokens=500, created_at=stale)
    budget = DailyBudget(db, user.id, 1000)

    assert await budget.remaining_tokens() == 1000


async def test_remaining_tokens_counts_usage_from_just_under_24_hours_ago(
    db: AsyncSession, user: User
) -> None:
    recent = datetime.now(UTC) - timedelta(hours=23, minutes=59)
    await add_usage(db, user.id, prompt_tokens=500, created_at=recent)
    budget = DailyBudget(db, user.id, 1000)

    assert await budget.remaining_tokens() == 500


async def test_remaining_tokens_never_goes_negative(db: AsyncSession, user: User) -> None:
    await add_usage(db, user.id, prompt_tokens=2000)
    budget = DailyBudget(db, user.id, 1000)

    assert await budget.remaining_tokens() == 0


async def test_remaining_tokens_is_scoped_to_the_owner(
    db: AsyncSession, user: User, other_user: User
) -> None:
    await add_usage(db, other_user.id, prompt_tokens=900)
    budget = DailyBudget(db, user.id, 1000)

    assert await budget.remaining_tokens() == 1000


# ---------------------------------------------------------------------------
# usage_by_task
# ---------------------------------------------------------------------------


async def test_usage_by_task_is_empty_with_no_usage(db: AsyncSession, user: User) -> None:
    assert await usage_by_task(db, user.id) == []


async def test_usage_by_task_sums_within_the_same_task_and_provider(
    db: AsyncSession, user: User
) -> None:
    await add_usage(
        db,
        user.id,
        task="tutor.chat",
        provider="anthropic",
        prompt_tokens=100,
        completion_tokens=50,
        cost_cents=1.0,
    )
    await add_usage(
        db,
        user.id,
        task="tutor.chat",
        provider="anthropic",
        prompt_tokens=200,
        completion_tokens=25,
        cost_cents=2.0,
    )

    rows = await usage_by_task(db, user.id)

    assert rows == [("tutor.chat", "anthropic", 300, 75, 3.0)]


async def test_usage_by_task_keeps_different_providers_separate(
    db: AsyncSession, user: User
) -> None:
    await add_usage(
        db, user.id, task="tutor.chat", provider="anthropic", prompt_tokens=10
    )
    await add_usage(db, user.id, task="tutor.chat", provider="ollama", prompt_tokens=20)

    rows = await usage_by_task(db, user.id)

    assert len(rows) == 2
    assert {(r[0], r[1]) for r in rows} == {
        ("tutor.chat", "anthropic"),
        ("tutor.chat", "ollama"),
    }


async def test_usage_by_task_respects_the_days_window(
    db: AsyncSession, user: User
) -> None:
    old = datetime.now(UTC) - timedelta(days=31)
    await add_usage(db, user.id, task="tutor.chat", prompt_tokens=999, created_at=old)

    assert await usage_by_task(db, user.id, days=30) == []


async def test_usage_by_task_is_scoped_to_the_owner(
    db: AsyncSession, user: User, other_user: User
) -> None:
    await add_usage(db, other_user.id, task="tutor.chat", prompt_tokens=100)

    assert await usage_by_task(db, user.id) == []
