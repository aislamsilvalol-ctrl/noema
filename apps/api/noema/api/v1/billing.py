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

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select

from noema.api.v1 import deps
from noema.db.models import Plan, PlanConfig
from noema.services.billing import BillingService, Interval
from noema.services.entitlements import (
    CREDITS_PER_FULL_LESSON,
    EntitlementsService,
    Mode,
    next_period_start,
)

router = APIRouter(
    prefix="/billing", tags=["billing"], dependencies=[Depends(deps.require_csrf)]
)
webhook_router = APIRouter(prefix="/billing", tags=["billing"])


class PlanOut(BaseModel):
    plan: Plan
    monthly_price_cents: int
    #: Null when the plan has no annual price (Free).
    annual_price_cents: int | None
    #: About how many lessons a month run in full mode before standard mode.
    full_lessons: int
    #: Lessons per week; null is no weekly limit.
    weekly_lessons: int | None
    #: Documents per month; null is no limit.
    monthly_documents: int | None
    #: Learning trails open at once; null is no limit.
    max_journeys: int | None
    #: Kept for clients that read it: the month's ceiling in credits.
    monthly_ai_units: int


class CheckoutIn(BaseModel):
    plan: Plan
    interval: Interval = Interval.MONTH


class CheckoutOut(BaseModel):
    url: str


class PlanStatusOut(BaseModel):
    """Where the learner stands this month, in the words the product uses:
    full lessons left and standard mode, never credits or tokens."""

    plan: Plan
    mode: Mode
    full_lessons_left: int
    #: When the month's full lessons come back.
    resets_at: datetime


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(db: deps.SessionDep) -> list[PlanOut]:
    """The plans on sale, straight from ``PlanConfig`` -- the same rows
    Stripe's own Price objects are expected to match. No auth required: a
    plan's price is not a secret, the same reasoning as ``meta.py``'s own
    unauthenticated routes.
    """
    result = await db.execute(
        select(PlanConfig).where(PlanConfig.active.is_(True)).order_by(PlanConfig.sort)
    )
    return [
        PlanOut(
            plan=row.plan,
            monthly_price_cents=row.monthly_price_cents,
            annual_price_cents=row.annual_price_cents,
            full_lessons=row.full_credits // CREDITS_PER_FULL_LESSON,
            weekly_lessons=row.weekly_lessons,
            monthly_documents=row.monthly_documents,
            max_journeys=row.max_journeys,
            monthly_ai_units=row.hard_credits,
        )
        for row in result.scalars().all()
    ]


@router.get("/status", response_model=PlanStatusOut)
async def plan_status(user: deps.CurrentUser, db: deps.SessionDep) -> PlanStatusOut:
    gate = await EntitlementsService(db, user).check_ai_usage()
    return PlanStatusOut(
        plan=gate.plan,
        mode=gate.mode,
        full_lessons_left=max(gate.full_credits - gate.used_credits, 0)
        // CREDITS_PER_FULL_LESSON,
        resets_at=next_period_start(),
    )


@router.post("/checkout", response_model=CheckoutOut)
async def create_checkout(
    payload: CheckoutIn,
    request: Request,
    user: deps.CurrentUser,
    db: deps.SessionDep,
    settings: deps.SettingsDep,
) -> CheckoutOut:
    url = await BillingService(db=db, settings=settings).create_checkout_session(
        user=user,
        plan=payload.plan,
        interval=payload.interval,
        request_origin=request.headers.get("origin"),
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
