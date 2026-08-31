"""Account: what you are, what you can take with you, and how to leave.

These are first-class endpoints rather than support tickets, because the README
promises both and a promise without an endpoint is a lie.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel

from noema.api.v1 import deps
from noema.core.logging import get_logger
from noema.db.base import utcnow
from noema.ingestion.storage import build_storage
from noema.services.account import GRACE_DAYS, build_export, request_deletion
from noema.services.billing import BillingService

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


class ConnectionOut(BaseModel):
    """What the API sees of your request, for calibrating the rate limiter.

    Authenticated, and about the caller's own connection only. `NOEMA_TRUSTED_PROXY_HOPS`
    has to match the deployment's actual proxy chain, and the number is not
    knowable from documentation — hosts add and remove hops. Guessing it wrong
    fails silently: the limit simply never bites, which is the failure mode this
    endpoint exists to end.
    """

    #: The socket address, which behind a proxy is the proxy.
    peer: str
    #: The chain as received, left to right.
    forwarded_for: list[str]
    trusted_hops: int
    #: Who the limiter is currently holding responsible.
    effective_client: str
    advice: str


@router.get("/connection", response_model=ConnectionOut)
async def connection(
    request: Request, user: deps.CurrentUser, settings: deps.SettingsDep
) -> ConnectionOut:
    """Show how this request arrived, so the hop count can be set from evidence."""
    from noema.api.middleware import _client_ip

    hops = [
        hop.strip()
        for hop in request.headers.get("x-forwarded-for", "").split(",")
        if hop.strip()
    ]
    peer = request.client.host if request.client else "unknown"
    effective = _client_ip(request, settings.noema_trusted_proxy_hops)

    if not hops:
        advice = (
            "No X-Forwarded-For. Either nothing is proxying this, or the proxy "
            "strips it — leave NOEMA_TRUSTED_PROXY_HOPS at 0."
        )
    elif effective == peer:
        advice = (
            f"The limiter is using the socket address. Set "
            f"NOEMA_TRUSTED_PROXY_HOPS to {len(hops)} to use the caller's."
        )
    else:
        advice = (
            f"The limiter is holding {effective} responsible. If that is not your "
            f"address, the hop count is wrong: the chain has {len(hops)} entries."
        )

    return ConnectionOut(
        peer=peer,
        forwarded_for=hops,
        trusted_hops=settings.noema_trusted_proxy_hops,
        effective_client=effective,
        advice=advice,
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
    user: deps.CurrentUser,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
    response: Response,
) -> DeletionOut:
    """Delete this account.

    The session ends immediately and the account stops working now; the data is
    purged after a grace period so a decision made at 2am can be undone. Export
    first — after the purge there is nothing to recover.

    Also cancels any active Stripe subscription. Leaving should stop the bill,
    not just the access — a subscriber who deletes their account and keeps
    getting charged for a product they can no longer open is exactly the kind
    of thing this endpoint's own docstring ("a promise without an endpoint is
    a lie") exists to prevent.
    """
    await BillingService(db=db, settings=settings).cancel_active_subscriptions(user=user)
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
