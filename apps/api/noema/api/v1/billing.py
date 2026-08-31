"""Stripe checkout, the customer portal, and the webhook -- the only writer of
``User.plan`` once Stripe is configured.

Two routers, deliberately: ``router`` carries ``require_csrf`` the way every
other cookie-mutating router in this codebase does (checkout/portal are
triggered by a logged-in browser). ``webhook_router`` does not -- its caller
is Stripe's own servers, which never hold a NOEMA session cookie, so
``require_csrf`` would reject every real webhook delivery with "Not
authenticated" before Stripe's own signature ever gets checked. The
signature check inside ``BillingService.handle_webhook`` (``stripe-signature``
against ``NOEMA_STRIPE_WEBHOOK_SECRET``) is what stands in for both
auth and CSRF on this one route.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select

from noema.api.v1 import deps
from noema.db.models import Plan, PlanConfig
from noema.services.billing import BillingService

router = APIRouter(
    prefix="/billing", tags=["billing"], dependencies=[Depends(deps.require_csrf)]
)
webhook_router = APIRouter(prefix="/billing", tags=["billing"])


class PlanOut(BaseModel):
    plan: Plan
    monthly_ai_units: int
    monthly_price_cents: int


class CheckoutIn(BaseModel):
    plan: Plan


class CheckoutOut(BaseModel):
    url: str


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(db: deps.SessionDep) -> list[PlanOut]:
    """Real prices, straight from ``PlanConfig`` -- the same row Stripe's own
    Price objects are expected to match. No auth required: a plan's price is
    not a secret, the same reasoning as ``meta.py``'s own unauthenticated
    routes.
    """
    result = await db.execute(select(PlanConfig).order_by(PlanConfig.monthly_price_cents))
    return [
        PlanOut(
            plan=row.plan,
            monthly_ai_units=row.monthly_ai_units,
            monthly_price_cents=row.monthly_price_cents,
        )
        for row in result.scalars().all()
    ]


@router.post("/checkout", response_model=CheckoutOut)
async def create_checkout(
    payload: CheckoutIn,
    request: Request,
    user: deps.CurrentUser,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
) -> CheckoutOut:
    url = await BillingService(db=db, settings=settings).create_checkout_session(
        user=user, plan=payload.plan, request_origin=request.headers.get("origin")
    )
    await db.commit()
    return CheckoutOut(url=url)


@router.post("/portal", response_model=CheckoutOut)
async def create_portal(
    request: Request,
    user: deps.CurrentUser,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
) -> CheckoutOut:
    url = await BillingService(db=db, settings=settings).create_portal_session(
        user=user, request_origin=request.headers.get("origin")
    )
    return CheckoutOut(url=url)


@webhook_router.post("/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request, db: deps.SessionDep, settings: deps.SettingsDep
) -> dict[str, bool]:
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    await BillingService(db=db, settings=settings).handle_webhook(
        payload=payload, signature=signature
    )
    await db.commit()
    return {"received": True}
