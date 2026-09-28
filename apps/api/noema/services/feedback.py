"""Reports from learners: a bug, a confusion, a bad reply, an idea.

The message is the learner's own words and may hold anything they typed,
so it is stored and read by admins and never written to a log line.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.errors import RateLimited
from noema.core.logging import get_logger
from noema.db.base import utcnow
from noema.db.models import FeedbackKind, FeedbackReport, User

log = get_logger(__name__)

#: One reporter's allowance. Ten is more than anyone writes by hand in an
#: hour and less than a script gets to fill the table with.
MAX_PER_HOUR = 10
WINDOW = timedelta(hours=1)

#: Column widths, applied here so a long path or a long browser string is
#: cut rather than refused — neither is the reporter's fault.
PAGE_MAX = 300
USER_AGENT_MAX = 300


@dataclass(frozen=True, slots=True)
class FeedbackRow:
    id: uuid.UUID
    kind: str
    message: str
    page: str | None
    user_agent: str | None
    created_at: datetime
    reporter_email: str


class FeedbackService:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    async def report(
        self,
        owner_id: uuid.UUID,
        *,
        kind: FeedbackKind,
        message: str,
        page: str | None,
        user_agent: str | None,
    ) -> FeedbackReport:
        # Counted in the table rather than in Redis: a report is already a
        # row, and one more query on an indexed pair is cheaper than a second
        # store that fails open. Two requests racing past the count both land;
        # eleven reports instead of ten is not a problem worth a lock.
        now = utcnow()
        recent = await self.db.scalar(
            select(func.count())
            .select_from(FeedbackReport)
            .where(
                FeedbackReport.owner_id == owner_id,
                FeedbackReport.created_at >= now - WINDOW,
            )
        )
        if (recent or 0) >= MAX_PER_HOUR:
            raise RateLimited(
                "That is a lot of reports for one hour. We have read them; "
                "try again later.",
                retry_after=int(WINDOW.total_seconds()),
            )

        row = FeedbackReport(
            owner_id=owner_id,
            kind=kind.value,
            message=message,
            page=page[:PAGE_MAX] if page else None,
            user_agent=user_agent[:USER_AGENT_MAX] if user_agent else None,
            # Stamped here, not by the database: inside one transaction
            # Postgres's now() is the same for every row, and the throttle
            # above compares against this clock.
            created_at=now,
        )
        self.db.add(row)
        await self.db.flush()
        # Kind and page only. The message is the learner's, not the log's.
        log.info("feedback.reported", kind=kind.value, page=row.page)
        return row

    async def recent(self, *, limit: int = 50) -> list[FeedbackRow]:
        """Newest first, with who sent each one. Admin-only by its caller;
        deliberately not scoped to an owner."""
        rows = await self.db.execute(
            select(FeedbackReport, User.email)
            .join(User, User.id == FeedbackReport.owner_id)
            .order_by(FeedbackReport.created_at.desc(), FeedbackReport.id.desc())
            .limit(limit)
        )
        return [
            FeedbackRow(
                id=report.id,
                kind=report.kind,
                message=report.message,
                page=report.page,
                user_agent=report.user_agent,
                created_at=report.created_at,
                reporter_email=email,
            )
            for report, email in rows.all()
        ]
