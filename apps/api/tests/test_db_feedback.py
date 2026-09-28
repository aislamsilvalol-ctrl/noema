"""Feedback reports: the learner's own words reach the admin, and nothing else.

Routes are called directly, as the rest of this suite does. ``deps.AdminUser``
is exercised in ``test_db_admin.py``; here the admin route gets a user and
the question is what it returns.
"""

from __future__ import annotations

import pytest
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.testing import capture_logs

from noema.api.v1.admin import list_feedback
from noema.api.v1.feedback import send_feedback
from noema.api.v1.schemas import FeedbackIn
from noema.core.errors import RateLimited
from noema.db.models import FeedbackKind, FeedbackReport, User
from noema.services.feedback import MAX_PER_HOUR, FeedbackService

pytestmark = pytest.mark.asyncio

BROWSER = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Safari/604.1"


def request_from(browser: str | None) -> Request:
    headers = [(b"user-agent", browser.encode())] if browser else []
    return Request(
        {
            "type": "http",
            "headers": headers,
            "client": ("10.0.0.1", 1234),
            "method": "POST",
            "path": "/api/v1/feedback",
        }
    )


async def test_a_report_keeps_the_page_and_the_browser(
    db: AsyncSession, user: User
) -> None:
    await send_feedback(
        FeedbackIn(
            kind=FeedbackKind.BUG, message="The card flipped twice.", page="/review"
        ),
        request_from(BROWSER),
        user,
        db,
    )

    row = await db.scalar(select(FeedbackReport))
    assert row is not None
    assert row.owner_id == user.id
    assert row.kind == "bug"
    assert row.message == "The card flipped twice."
    assert row.page == "/review"
    assert row.user_agent == BROWSER


async def test_a_report_without_context_is_still_a_report(
    db: AsyncSession, user: User
) -> None:
    await send_feedback(
        FeedbackIn(kind=FeedbackKind.IDEA, message="Dark mode on the map."),
        request_from(None),
        user,
        db,
    )

    row = await db.scalar(select(FeedbackReport))
    assert row is not None
    assert row.page is None
    assert row.user_agent is None


async def test_a_long_page_or_browser_string_is_cut_not_refused(
    db: AsyncSession, user: User
) -> None:
    await FeedbackService(db).report(
        user.id,
        kind=FeedbackKind.CONFUSION,
        message="x",
        page="/" + "a" * 400,
        user_agent="b" * 400,
    )

    row = await db.scalar(select(FeedbackReport))
    assert row is not None
    assert len(row.page or "") == 300
    assert len(row.user_agent or "") == 300


async def test_the_message_is_never_logged(db: AsyncSession, user: User) -> None:
    secret = "my password is hunter2 and the card was wrong"

    with capture_logs() as logs:
        await FeedbackService(db).report(
            user.id, kind=FeedbackKind.BUG, message=secret, page="/today", user_agent=None
        )

    events = [entry for entry in logs if entry["event"] == "feedback.reported"]
    assert len(events) == 1
    assert events[0]["kind"] == "bug"
    assert events[0]["page"] == "/today"
    assert not any(secret in str(value) for entry in logs for value in entry.values())


async def test_one_reporter_gets_ten_an_hour_and_others_are_unaffected(
    db: AsyncSession, user: User, other_user: User
) -> None:
    service = FeedbackService(db)
    for n in range(MAX_PER_HOUR):
        await service.report(
            user.id,
            kind=FeedbackKind.IDEA,
            message=f"idea {n}",
            page=None,
            user_agent=None,
        )

    with pytest.raises(RateLimited):
        await service.report(
            user.id,
            kind=FeedbackKind.IDEA,
            message="one more",
            page=None,
            user_agent=None,
        )

    await service.report(
        other_user.id, kind=FeedbackKind.BUG, message="mine", page=None, user_agent=None
    )
    count = len((await db.scalars(select(FeedbackReport))).all())
    assert count == MAX_PER_HOUR + 1


async def test_admins_read_every_report_newest_first_with_who_sent_it(
    db: AsyncSession, user: User, other_user: User
) -> None:
    service = FeedbackService(db)
    await service.report(
        user.id,
        kind=FeedbackKind.AI_QUALITY,
        message="first",
        page="/chat",
        user_agent=None,
    )
    await service.report(
        other_user.id, kind=FeedbackKind.BUG, message="second", page=None, user_agent=None
    )

    rows = await list_feedback(user, db, limit=50)

    assert [(r.message, r.reporter_email) for r in rows] == [
        ("second", other_user.email),
        ("first", user.email),
    ]
    assert rows[1].kind == "ai_quality"
    assert rows[1].page == "/chat"


async def test_the_admin_list_honours_its_limit(db: AsyncSession, user: User) -> None:
    service = FeedbackService(db)
    for n in range(3):
        await service.report(
            user.id, kind=FeedbackKind.IDEA, message=str(n), page=None, user_agent=None
        )

    rows = await list_feedback(user, db, limit=2)

    assert [r.message for r in rows] == ["2", "1"]
