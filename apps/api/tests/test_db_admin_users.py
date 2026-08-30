"""AdminUsersService: the full user roster, real usage per user, and the one
manual plan-change lever that exists before Phase 8's Stripe webhooks can
drive this from a real subscription event.

Same non-scoping discipline as ``admin_intelligence.py``: an admin listing
users must see every user, not just the caller -- getting that backwards
silently under-reports rather than leaks, but is just as wrong for a page
whose whole point is showing every account on the platform.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from noema.api.v1 import admin
from noema.core.errors import NotFound
from noema.db.models import AIUsage, Plan, User
from noema.services.admin_users import AdminUsersService

pytestmark = pytest.mark.asyncio


def _usage(
    *, owner_id: uuid.UUID, prompt_tokens: int, completion_tokens: int = 0
) -> AIUsage:
    return AIUsage(
        owner_id=owner_id,
        provider="anthropic",
        model="claude-sonnet-5",
        task="tutor_chat",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_cents=1.0,
        succeeded=True,
        created_at=datetime.now(UTC),
    )


async def test_lists_every_user_not_just_the_caller(
    db: AsyncSession, user: User, other_user: User
) -> None:
    rows, _ = await AdminUsersService(db).list_users()

    ids = {r.id for r in rows}
    assert user.id in ids
    assert other_user.id in ids


async def test_usage_is_computed_per_user_across_the_whole_roster(
    db: AsyncSession, user: User, other_user: User
) -> None:
    db.add(_usage(owner_id=user.id, prompt_tokens=5_000))
    db.add(_usage(owner_id=other_user.id, prompt_tokens=1_000))
    await db.flush()

    rows, _ = await AdminUsersService(db).list_users()

    by_id = {r.id: r for r in rows}
    assert by_id[user.id].used_units_this_period == 5
    assert by_id[other_user.id].used_units_this_period == 1


async def test_search_matches_email_case_insensitively(
    db: AsyncSession, user: User, other_user: User
) -> None:
    rows, _ = await AdminUsersService(db).list_users(search=user.email.upper()[:6])

    ids = {r.id for r in rows}
    assert user.id in ids
    assert other_user.id not in ids


async def test_pagination_returns_a_cursor_when_more_rows_remain(
    db: AsyncSession, user: User, other_user: User
) -> None:
    rows, next_cursor = await AdminUsersService(db).list_users(limit=1)

    assert len(rows) == 1
    assert next_cursor is not None


async def test_set_plan_writes_the_real_column_and_is_visible_immediately(
    db: AsyncSession, user: User, other_user: User
) -> None:
    row = await AdminUsersService(db).set_plan(
        admin=user, target_user_id=other_user.id, plan=Plan.PRO
    )

    assert row.plan == Plan.PRO
    await db.refresh(other_user)
    assert other_user.plan == Plan.PRO


async def test_set_plan_on_an_unknown_user_is_not_found(
    db: AsyncSession, user: User
) -> None:
    with pytest.raises(NotFound):
        await AdminUsersService(db).set_plan(
            admin=user, target_user_id=uuid.uuid4(), plan=Plan.PRO
        )


async def test_list_users_route_returns_a_page(db: AsyncSession, user: User) -> None:
    page = await admin.list_users(user=user, db=db, cursor=None, search=None, limit=50)

    assert any(item.id == user.id for item in page.items)


async def test_set_user_plan_route_updates_and_returns_the_row(
    db: AsyncSession, user: User, other_user: User
) -> None:
    out = await admin.set_user_plan(
        target_user_id=other_user.id,
        payload=admin.SetPlanIn(plan=Plan.MAX),
        user=user,
        db=db,
    )

    assert out.plan == Plan.MAX
    assert out.id == other_user.id
