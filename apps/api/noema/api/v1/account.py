"""Account: what you are, what you can take with you, and how to leave.

These are first-class endpoints rather than support tickets, because the README
promises both and a promise without an endpoint is a lie.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from noema.api.v1 import deps
from noema.core.logging import get_logger
from noema.db.base import utcnow
from noema.ingestion.storage import build_storage
from noema.services.account import GRACE_DAYS, build_export, request_deletion

log = get_logger(__name__)

router = APIRouter(
    prefix="/me", tags=["account"], dependencies=[Depends(deps.require_csrf)]
)


class AccountOut(BaseModel):
    email: str
    display_name: str
    created_at: datetime


class DeletionOut(BaseModel):
    deleted_at: datetime
    purge_after: datetime
    grace_days: int
    detail: str


@router.get("", response_model=AccountOut)
async def me(user: deps.CurrentUser) -> AccountOut:
    return AccountOut(
        email=user.email, display_name=user.display_name, created_at=user.created_at
    )


@router.post("/export")
async def export(
    user: deps.CurrentUser, db: deps.SessionDep, settings: deps.SettingsDep
) -> Response:
    """Download everything this account owns.

    Notes as Markdown, uploads unchanged, structure as JSON — an archive that is
    useful without NOEMA.
    """
    archive = await build_export(db, user, storage=build_storage(settings))
    filename = f"noema-export-{utcnow():%Y-%m-%d}.zip"

    log.info("account.exported", user_id=str(user.id), bytes=len(archive))
    return Response(
        content=archive,
        media_type="application/zip",
        headers={"content-disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("", response_model=DeletionOut, status_code=status.HTTP_200_OK)
async def delete_account(
    user: deps.CurrentUser, db: deps.SessionDep, response: Response
) -> DeletionOut:
    """Delete this account.

    The session ends immediately and the account stops working now; the data is
    purged after a grace period so a decision made at 2am can be undone. Export
    first — after the purge there is nothing to recover.
    """
    request = await request_deletion(db, user)

    response.delete_cookie(deps.SESSION_COOKIE, path="/")
    response.delete_cookie(deps.CSRF_COOKIE, path="/")

    return DeletionOut(
        deleted_at=request.requested_at,
        purge_after=request.purge_after,
        grace_days=GRACE_DAYS,
        detail=(
            f"Your account is closed and you have been signed out. Everything is "
            f"permanently deleted after {GRACE_DAYS} days — contact the operator of "
            "this deployment before then if this was a mistake."
        ),
    )
