"""Admin-only business data: real usage/cost from ``AIUsage``, and a what-if
economics simulator. Gated by ``deps.AdminUser`` -- see its own docstring for
why this is an email allowlist, not a role table.

``deps.AdminUser`` resolves through ``get_session_user``, cookie-only -- the
same shape ``require_csrf`` exists to protect, and every other cookie-mutating
router in this codebase carries it at the router level (``ai``, ``imports``,
``exports``, ``notes``, ``account``, ``concepts``, ``tokens``, ``study``,
``library``, ``sources``). This router mutates now too (``set_user_plan``),
so it needs the same guard -- ``require_csrf`` no-ops on safe methods, so the
GET routes here are unaffected.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field, model_validator

from noema.api.v1 import deps
from noema.api.v1.schemas import Page
from noema.db.base import utcnow
from noema.db.models import ModelTier, Plan
from noema.services.admin_intelligence import AdminIntelligenceService
from noema.services.admin_reports import AdminReportsService
from noema.services.admin_users import AdminUsersService
from noema.services.economics import (
    DEFAULT_BILLING_FEE_PERCENT,
    DEFAULT_PAYMENT_FEE_FIXED_CENTS,
    DEFAULT_PAYMENT_FEE_PERCENT,
    DEFAULT_TAX_PERCENT,
    EconomicsSimulator,
    SimulatorInputs,
)
from noema.services.professor_economy import ProfessorEconomyService

router = APIRouter(
    prefix="/admin", tags=["admin"], dependencies=[Depends(deps.require_csrf)]
)


class TopUserOut(BaseModel):
    user_id: uuid.UUID
    email: str
    spend_cents: float


class IntelligenceOut(BaseModel):
    requests_today: int
    tokens_today: int
    spend_today_cents: float
    spend_this_month_cents: float
    error_rate: float
    tier_mix: dict[str, float]
    top_users: list[TopUserOut]
    #: Named plainly so a dashboard consumer never mistakes an absent metric
    #: for a real zero -- cache-hit-rate and RAG-call-count aren't
    #: instrumented anywhere queryable yet (see admin_intelligence.py).
    not_yet_tracked: list[str] = Field(
        default=["cache_hit_rate", "rag_calls", "latency_p50_ms"]
    )


@router.get("/intelligence", response_model=IntelligenceOut)
async def intelligence(user: deps.AdminUser, db: deps.SessionDep) -> IntelligenceOut:
    snapshot = await AdminIntelligenceService(db).snapshot()
    return IntelligenceOut(
        requests_today=snapshot.requests_today,
        tokens_today=snapshot.tokens_today,
        spend_today_cents=snapshot.spend_today_cents,
        spend_this_month_cents=snapshot.spend_this_month_cents,
        error_rate=snapshot.error_rate,
        tier_mix=snapshot.tier_mix,
        top_users=[
            TopUserOut(user_id=u.user_id, email=u.email, spend_cents=u.spend_cents)
            for u in snapshot.top_users
        ],
    )


class FeatureUsageOut(BaseModel):
    feature: str
    calls: int
    prompt_tokens: int
    cached_tokens: int
    completion_tokens: int
    cost_cents: float


class ProfessorEconomyOut(BaseModel):
    """What teaching cost this month, from the recorded rows — see
    ``noema/services/professor_economy.py``. ``None`` means "cannot be
    computed from what was recorded", never zero."""

    features: list[FeatureUsageOut]
    calls: int
    prompt_tokens: int
    cached_tokens: int
    completion_tokens: int
    cost_cents: float
    cache_hit_rate: float | None
    compaction_tokens_saved: int
    compactions: int
    lessons: int
    cost_per_lesson_cents: float | None
    active_learners: int
    cost_per_learner_cents: float | None


@router.get("/professor-economy", response_model=ProfessorEconomyOut)
async def professor_economy(
    user: deps.AdminUser, db: deps.SessionDep
) -> ProfessorEconomyOut:
    snapshot = await ProfessorEconomyService(db).snapshot()
    return ProfessorEconomyOut(
        features=[FeatureUsageOut(**vars(f)) for f in snapshot.features],
        calls=snapshot.calls,
        prompt_tokens=snapshot.prompt_tokens,
        cached_tokens=snapshot.cached_tokens,
        completion_tokens=snapshot.completion_tokens,
        cost_cents=snapshot.cost_cents,
        cache_hit_rate=snapshot.cache_hit_rate,
        compaction_tokens_saved=snapshot.compaction_tokens_saved,
        compactions=snapshot.compactions,
        lessons=snapshot.lessons,
        cost_per_lesson_cents=snapshot.cost_per_lesson_cents,
        active_learners=snapshot.active_learners,
        cost_per_learner_cents=snapshot.cost_per_learner_cents,
    )


class SimulatorIn(BaseModel):
    subscribers: int = Field(ge=0)
    messages_per_day: float = Field(ge=0)
    avg_input_tokens: int = Field(ge=0)
    avg_output_tokens: int = Field(ge=0)
    #: Tier name -> fraction, must sum to ~1.0. A plan with e.g. no premium
    #: usage can omit that key rather than send 0.0.
    tier_mix: dict[ModelTier, float]
    active_days_per_month: float = Field(ge=0, le=31)
    plan_price_cents: float = Field(ge=0)
    payment_fee_percent: float = DEFAULT_PAYMENT_FEE_PERCENT
    payment_fee_fixed_cents: float = DEFAULT_PAYMENT_FEE_FIXED_CENTS
    billing_fee_percent: float = DEFAULT_BILLING_FEE_PERCENT
    tax_percent: float = DEFAULT_TAX_PERCENT

    @model_validator(mode="after")
    def _tier_mix_sums_to_one(self) -> SimulatorIn:
        total = sum(self.tier_mix.values())
        # Tolerant of float rounding from a UI slider, not of a genuinely
        # incomplete mix -- 0.6/0.35/0.05 typed by hand should pass.
        if self.tier_mix and abs(total - 1.0) > 0.01:
            raise ValueError(f"tier_mix must sum to 1.0, got {total}")
        return self


class SimulatorOut(BaseModel):
    ai_cost_per_user_cents: float
    ai_cost_total_cents: float
    payment_fees_cents: float
    gross_revenue_cents: float
    net_revenue_cents: float
    gross_margin_percent: float
    #: A projection from the inputs above, never a live figure -- see
    #: EconomicsSimulator's own module docstring.
    estimated_mrr_cents: float


@router.post("/simulator", response_model=SimulatorOut)
async def simulator(
    payload: SimulatorIn, user: deps.AdminUser, db: deps.SessionDep
) -> SimulatorOut:
    result = await EconomicsSimulator(db).simulate(
        SimulatorInputs(
            subscribers=payload.subscribers,
            messages_per_day=payload.messages_per_day,
            avg_input_tokens=payload.avg_input_tokens,
            avg_output_tokens=payload.avg_output_tokens,
            tier_mix=payload.tier_mix,
            active_days_per_month=payload.active_days_per_month,
            plan_price_cents=payload.plan_price_cents,
            payment_fee_percent=payload.payment_fee_percent,
            payment_fee_fixed_cents=payload.payment_fee_fixed_cents,
            billing_fee_percent=payload.billing_fee_percent,
            tax_percent=payload.tax_percent,
        )
    )
    return SimulatorOut(
        ai_cost_per_user_cents=result.ai_cost_per_user_cents,
        ai_cost_total_cents=result.ai_cost_total_cents,
        payment_fees_cents=result.payment_fees_cents,
        gross_revenue_cents=result.gross_revenue_cents,
        net_revenue_cents=result.net_revenue_cents,
        gross_margin_percent=result.gross_margin_percent,
        estimated_mrr_cents=result.estimated_mrr_cents,
    )


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    plan: Plan
    created_at: datetime
    used_units_this_period: int
    limit_units: int


@router.get("/users", response_model=Page[AdminUserOut])
async def list_users(
    user: deps.AdminUser,
    db: deps.SessionDep,
    cursor: uuid.UUID | None = None,
    search: str | None = None,
    limit: int = 50,
) -> Page[AdminUserOut]:
    rows, next_cursor = await AdminUsersService(db).list_users(
        limit=limit, cursor=cursor, search=search
    )
    return Page(
        items=[
            AdminUserOut(
                id=r.id,
                email=r.email,
                display_name=r.display_name,
                plan=r.plan,
                created_at=r.created_at,
                used_units_this_period=r.used_units_this_period,
                limit_units=r.limit_units,
            )
            for r in rows
        ],
        next_cursor=next_cursor,
    )


class SetPlanIn(BaseModel):
    plan: Plan


@router.patch(
    "/users/{target_user_id}/plan",
    response_model=AdminUserOut,
    status_code=status.HTTP_200_OK,
)
async def set_user_plan(
    target_user_id: uuid.UUID,
    payload: SetPlanIn,
    user: deps.AdminUser,
    db: deps.SessionDep,
) -> AdminUserOut:
    """Manually change a user's plan -- the only lever that exists before
    Phase 8's Stripe webhooks can drive this from a real subscription event.
    Every change is logged (see ``AdminUsersService.set_plan``).
    """
    row = await AdminUsersService(db).set_plan(
        admin=user, target_user_id=target_user_id, plan=payload.plan
    )
    return AdminUserOut(
        id=row.id,
        email=row.email,
        display_name=row.display_name,
        plan=row.plan,
        created_at=row.created_at,
        used_units_this_period=row.used_units_this_period,
        limit_units=row.limit_units,
    )


class PlanReportOut(BaseModel):
    plan: Plan
    user_count: int
    #: Real: this plan's users' actual AI spend this calendar month.
    real_cost_cents: float
    #: A projection ("if these users were being billed at this plan's
    #: published price"), never a fact -- there is no Stripe integration yet,
    #: so nobody on a paid plan is actually paying.
    projected_revenue_if_billed_cents: int
    projected_margin_if_billed_cents: float


@router.get("/reports/profit", response_model=list[PlanReportOut])
async def profit_report(user: deps.AdminUser, db: deps.SessionDep) -> list[PlanReportOut]:
    rows = await AdminReportsService(db).profit_projection()
    return [
        PlanReportOut(
            plan=r.plan,
            user_count=r.user_count,
            real_cost_cents=r.real_cost_cents,
            projected_revenue_if_billed_cents=r.projected_revenue_if_billed_cents,
            projected_margin_if_billed_cents=r.projected_margin_if_billed_cents,
        )
        for r in rows
    ]


@router.get("/reports/users.csv")
async def export_users_report(user: deps.AdminUser, db: deps.SessionDep) -> Response:
    """Every user on the platform, one row each -- the same data
    ``GET /admin/users`` paginates through, flattened for a spreadsheet.
    """
    csv_data = await AdminReportsService(db).export_users_csv()
    filename = f"noema-users-{utcnow():%Y-%m-%d}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"content-disposition": f'attachment; filename="{filename}"'},
    )
