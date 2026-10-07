"""The launch dashboard: the funnel from signup to a successful learning
session, retention, revenue and what the AI cost -- from the database.

Every learning number goes through `noema.services.launch_definitions`; this
module only windows and groups. One query per metric family, each a
``date_trunc``/``GROUP BY`` over an indexed range, never a query per user or
per day. Days are UTC.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import DateTime, case, cast, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.base import utcnow
from noema.db.models import (
    AIUsage,
    FeedbackReport,
    FocusSession,
    LearningLifecycleEvent,
    Plan,
    PlanConfig,
    User,
)
from noema.services import launch_definitions as d
from noema.services.learning_events import LESSON_COMPLETED, LESSON_STARTED

#: Metrics the dashboard would show if anything recorded them.
NOT_RECORDED = ["ai_latency_ms"]


@dataclass(slots=True)
class LaunchDay:
    day: date
    signups: int = 0
    #: Of that day's signups, how many activated (so far, if under 7 days old).
    activated: int = 0
    dau: int = 0
    lessons_started: int = 0
    lessons_completed: int = 0
    focus_started: int = 0
    focus_completed: int = 0
    successful_sessions: int = 0
    ai_calls: int = 0
    ai_failures: int = 0
    ai_cost_cents: float = 0.0


@dataclass(slots=True)
class LaunchWeek:
    week_start: date
    active_learners: int
    successful_sessions: int
    north_star: float | None


@dataclass(slots=True)
class PlanRevenue:
    plan: str
    #: Paid through Stripe: a paid plan on an account with a Stripe customer.
    paying: int
    #: A paid plan set by hand (`PATCH /admin/users/{id}/plan`), no Stripe.
    comped: int
    price_cents: int
    mrr_cents: int


@dataclass(slots=True)
class LaunchReport:
    days: int
    window_start: date
    window_end: date
    generated_at: datetime
    daily: list[LaunchDay]
    weekly: list[LaunchWeek]
    signups: int
    activated: int
    #: Signups old enough (≥ 7 days) to have had their whole window.
    activation_cohort: int
    activation_cohort_activated: int
    activation_rate: float | None
    dau: int
    wau: int
    lessons_started: int
    lessons_completed: int
    successful_sessions: dict[str, int]
    north_star: float | None
    d1_cohort: int
    d1_retained: int
    d1_rate: float | None
    d7_cohort: int
    d7_retained: int
    d7_rate: float | None
    revenue: list[PlanRevenue]
    paying_users: int
    mrr_cents: int
    ai_calls: int
    ai_failures: int
    ai_failure_rate: float | None
    ai_cost_cents: float
    ai_latency_p50_ms: float | None
    ai_latency_p95_ms: float | None
    feedback_reports: int
    focus_started: int
    focus_completed: int
    definitions: dict[str, str] = field(default_factory=lambda: dict(d.DEFINITIONS))
    not_recorded: list[str] = field(default_factory=lambda: list(NOT_RECORDED))


def _rate(part: int, whole: int) -> float | None:
    return part / whole if whole else None


async def build_launch_report(
    db: AsyncSession, *, days: int, now: datetime | None = None
) -> LaunchReport:
    now = now or utcnow()
    today = now.astimezone(UTC).date()
    end = datetime.combine(today + timedelta(days=1), time(), UTC)
    start = end - timedelta(days=days)
    by_day = {
        start.date() + timedelta(days=i): LaunchDay(start.date() + timedelta(days=i))
        for i in range(days)
    }

    # Signups and activation, by signup day.
    acts = d.activations(start, end).subquery()
    signup_day = d.utc_day(acts.c.signed_up_at)
    mature = acts.c.signed_up_at + d.ACTIVATION_WINDOW <= now
    cohort_rows = await db.execute(
        select(
            signup_day,
            func.count(),
            func.count(acts.c.activated_at),
            func.count().filter(mature),
            func.count(acts.c.activated_at).filter(mature),
        ).group_by(signup_day)
    )
    activation_cohort = activation_cohort_activated = 0
    for day, signups, activated, mature_n, mature_activated in cohort_rows:
        by_day[day].signups = signups
        by_day[day].activated = activated
        activation_cohort += mature_n
        activation_cohort_activated += mature_activated

    # DAU, and active learners per ISO week and over the last 7 days.
    learner_days = d.active_learner_days(start, end).subquery()
    for day, count in await db.execute(
        select(learner_days.c.day, func.count()).group_by(learner_days.c.day)
    ):
        by_day[day].dau = count
    week = func.date_trunc("week", cast(learner_days.c.day, DateTime))
    wau_by_week = {
        w.date(): n
        for w, n in await db.execute(
            select(week, func.count(distinct(learner_days.c.owner_id))).group_by(week)
        )
    }
    trailing_from = today - timedelta(days=6)
    wau = (
        await db.scalar(
            select(func.count(distinct(learner_days.c.owner_id))).where(
                learner_days.c.day >= trailing_from
            )
        )
        or 0
    )

    # Lessons started and completed.
    lesson_day = d.utc_day(LearningLifecycleEvent.created_at)
    for day, kind, count in await db.execute(
        select(lesson_day, LearningLifecycleEvent.kind, func.count())
        .where(
            LearningLifecycleEvent.kind.in_((LESSON_STARTED, LESSON_COMPLETED)),
            LearningLifecycleEvent.created_at >= start,
            LearningLifecycleEvent.created_at < end,
        )
        .group_by(lesson_day, LearningLifecycleEvent.kind)
    ):
        if kind == LESSON_STARTED:
            by_day[day].lessons_started = count
        else:
            by_day[day].lessons_completed = count

    # Focus sessions started and completed.
    started_day = d.utc_day(FocusSession.started_at)
    for day, count in await db.execute(
        select(started_day, func.count())
        .where(FocusSession.started_at >= start, FocusSession.started_at < end)
        .group_by(started_day)
    ):
        by_day[day].focus_started = count
    completed_day = d.utc_day(FocusSession.completed_at)
    for day, count in await db.execute(
        select(completed_day, func.count())
        .where(
            FocusSession.status == "completed",
            FocusSession.completed_at >= start,
            FocusSession.completed_at < end,
        )
        .group_by(completed_day)
    ):
        by_day[day].focus_completed = count

    # Successful sessions, by day and kind.
    sessions = d.successful_sessions(start, end).subquery()
    session_day = d.utc_day(sessions.c.occurred_at)
    by_kind: dict[str, int] = {
        d.SESSION_TEACHING: 0,
        d.SESSION_FOCUS: 0,
        d.SESSION_REVIEW: 0,
    }
    trailing_successful = 0
    for day, kind, count in await db.execute(
        select(session_day, sessions.c.kind, func.count()).group_by(
            session_day, sessions.c.kind
        )
    ):
        by_day[day].successful_sessions += count
        by_kind[kind] += count
        if day >= trailing_from:
            trailing_successful += count

    successful_by_week: dict[date, int] = defaultdict(int)
    for row in by_day.values():
        successful_by_week[row.day - timedelta(days=row.day.weekday())] += (
            row.successful_sessions
        )
    weekly = [
        LaunchWeek(
            week_start=w,
            active_learners=wau_by_week.get(w, 0),
            successful_sessions=successful_by_week[w],
            north_star=_rate(successful_by_week[w], wau_by_week.get(w, 0)),
        )
        for w in sorted(successful_by_week)
    ]

    # D1/D7 retention, by signup cohort: active on exactly the 1st / 7th day
    # after signing up. A cohort counts once that day has fully passed.
    cohort = (
        select(User.id.label("id"), d.utc_day(User.created_at).label("signup_day"))
        .where(User.created_at >= start, User.created_at < end)
        .subquery()
    )
    gap = learner_days.c.day - cohort.c.signup_day
    d1 = d7 = d1_cohort = d7_cohort = 0
    for cohort_day, n, back_d1, back_d7 in await db.execute(
        select(
            cohort.c.signup_day,
            func.count(distinct(cohort.c.id)),
            func.count(distinct(case((gap == 1, cohort.c.id)))),
            func.count(distinct(case((gap == 7, cohort.c.id)))),
        )
        .select_from(cohort)
        .outerjoin(learner_days, learner_days.c.owner_id == cohort.c.id)
        .group_by(cohort.c.signup_day)
    ):
        if cohort_day + timedelta(days=1) < today:
            d1_cohort += n
            d1 += back_d1
        if cohort_day + timedelta(days=7) < today:
            d7_cohort += n
            d7 += back_d7

    # Paying users and MRR, now (not windowed). A webhook moves a cancelled
    # or deleted subscription back to Free, so a paid plan on an account with
    # a Stripe customer is a live subscription.
    price_rows = await db.execute(select(PlanConfig.plan, PlanConfig.monthly_price_cents))
    prices = dict(price_rows.tuples().all())
    on_stripe = User.stripe_customer_id.is_not(None)
    plan_counts = {
        plan: (paying, comped)
        for plan, paying, comped in await db.execute(
            select(
                User.plan,
                func.count().filter(on_stripe),
                func.count().filter(~on_stripe),
            )
            .where(User.deleted_at.is_(None), User.plan != Plan.FREE)
            .group_by(User.plan)
        )
    }
    revenue = []
    for plan in Plan:
        if plan is Plan.FREE:
            continue
        paying, comped = plan_counts.get(plan, (0, 0))
        price = prices.get(plan, 0)
        revenue.append(
            PlanRevenue(
                plan=plan.value,
                paying=paying,
                comped=comped,
                price_cents=price,
                mrr_cents=paying * price,
            )
        )

    # AI calls, failures and cost.
    ai_day = d.utc_day(AIUsage.created_at)
    for day, calls, failures, cost in await db.execute(
        select(
            ai_day,
            func.count(),
            func.count().filter(AIUsage.succeeded.is_(False)),
            func.coalesce(func.sum(AIUsage.cost_cents), 0.0),
        )
        .where(AIUsage.created_at >= start, AIUsage.created_at < end)
        .group_by(ai_day)
    ):
        by_day[day].ai_calls = calls
        by_day[day].ai_failures = failures
        by_day[day].ai_cost_cents = float(cost)

    feedback = (
        await db.scalar(
            select(func.count()).where(
                FeedbackReport.created_at >= start, FeedbackReport.created_at < end
            )
        )
        or 0
    )

    daily = list(by_day.values())
    ai_calls = sum(r.ai_calls for r in daily)
    ai_failures = sum(r.ai_failures for r in daily)
    return LaunchReport(
        days=days,
        window_start=start.date(),
        window_end=today,
        generated_at=now,
        daily=daily,
        weekly=weekly,
        signups=sum(r.signups for r in daily),
        activated=sum(r.activated for r in daily),
        activation_cohort=activation_cohort,
        activation_cohort_activated=activation_cohort_activated,
        activation_rate=_rate(activation_cohort_activated, activation_cohort),
        dau=by_day[today].dau,
        wau=wau,
        lessons_started=sum(r.lessons_started for r in daily),
        lessons_completed=sum(r.lessons_completed for r in daily),
        successful_sessions=by_kind,
        north_star=_rate(trailing_successful, wau),
        d1_cohort=d1_cohort,
        d1_retained=d1,
        d1_rate=_rate(d1, d1_cohort),
        d7_cohort=d7_cohort,
        d7_retained=d7,
        d7_rate=_rate(d7, d7_cohort),
        revenue=revenue,
        paying_users=sum(r.paying for r in revenue),
        mrr_cents=sum(r.mrr_cents for r in revenue),
        ai_calls=ai_calls,
        ai_failures=ai_failures,
        ai_failure_rate=_rate(ai_failures, ai_calls),
        ai_cost_cents=round(sum(r.ai_cost_cents for r in daily), 4),
        ai_latency_p50_ms=None,
        ai_latency_p95_ms=None,
        feedback_reports=feedback,
        focus_started=sum(r.focus_started for r in daily),
        focus_completed=sum(r.focus_completed for r in daily),
    )
