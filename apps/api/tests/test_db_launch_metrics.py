"""The launch definitions (activation, successful session) over synthetic rows,
the dashboard built from them, and the route's gate.

Every row is dated explicitly: the definitions are windows, and a test that
leaned on ``now()`` would pass or fail by the calendar.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.api.v1 import deps
from noema.api.v1.schemas import RegisterRequest, SignupAttribution
from noema.core import totp
from noema.core.config import Settings, get_settings
from noema.core.crypto import SecretBox
from noema.db.base import get_session
from noema.db.models import (
    Card,
    CardOrigin,
    FocusSession,
    LearningJourney,
    LearningLifecycleEvent,
    MasteryEvent,
    Notebook,
    Plan,
    PlanConfig,
    Review,
    Subject,
    TeachingSession,
    TeachingTurn,
    TurnRole,
    User,
    Workspace,
)
from noema.main import app
from noema.services import launch_definitions as d
from noema.services.auth import AuthService
from noema.services.launch_dashboard import build_launch_report
from noema.services.mfa import MfaService

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 9, 25, 15, 0, tzinfo=UTC)
WINDOW = (NOW - timedelta(days=30), NOW + timedelta(days=1))


async def make_user(db: AsyncSession, signed_up: datetime, **extra: object) -> User:
    user = User(
        email=f"u-{uuid.uuid4().hex[:10]}@example.com",
        password_hash="x",
        display_name="Learner",
        created_at=signed_up,
        **extra,
    )
    db.add(user)
    await db.flush()
    return user


async def lesson(
    db: AsyncSession, user: User, at: datetime, *, learner_turn: bool = True
) -> TeachingSession:
    journey = LearningJourney(owner_id=user.id, goal="cálculo")
    db.add(journey)
    await db.flush()
    session = TeachingSession(owner_id=user.id, journey_id=journey.id)
    db.add(session)
    await db.flush()
    if learner_turn:
        db.add(
            TeachingTurn(
                owner_id=user.id,
                session_id=session.id,
                role=TurnRole.LEARNER,
                content="oi",
                created_at=at,
            )
        )
    await db.flush()
    return session


def showing(
    user: User,
    session: TeachingSession,
    at: datetime,
    *,
    kind: str = "quiz",
    score: float = 1.0,
    in_session: bool = True,
) -> MasteryEvent:
    assert session.journey_id is not None
    return MasteryEvent(
        owner_id=user.id,
        journey_id=session.journey_id,
        session_id=session.id if in_session else None,
        concept_name="limite",
        kind=kind,
        score=score,
        created_at=at,
    )


async def activated_at(db: AsyncSession, user: User) -> datetime | None:
    rows = await db.execute(d.activations(*WINDOW))
    found = {r.user_id: r.activated_at for r in rows}
    assert user.id in found
    value: datetime | None = found[user.id]
    return value


async def cards(db: AsyncSession, user: User, n: int) -> list[Card]:
    ws = Workspace(owner_id=user.id, title="W", slug=f"w-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    await db.flush()
    subject = Subject(owner_id=user.id, workspace_id=ws.id, title="S", slug="s")
    db.add(subject)
    await db.flush()
    nb = Notebook(
        owner_id=user.id,
        subject_id=subject.id,
        title="N",
        slug="n",
        retrieval_settings={},
    )
    db.add(nb)
    await db.flush()
    made = [
        Card(
            owner_id=user.id,
            notebook_id=nb.id,
            front_md="Q",
            back_md="A",
            origin=CardOrigin.USER,
            source_chunk_ids=[],
        )
        for _ in range(n)
    ]
    db.add_all(made)
    await db.flush()
    return made


async def rate(db: AsyncSession, user: User, made: list[Card], at: datetime) -> None:
    db.add_all(
        Review(
            owner_id=user.id,
            card_id=c.id,
            rating=3,
            state_after={},
            reviewed_at=at + timedelta(minutes=i),
        )
        for i, c in enumerate(made)
    )
    await db.flush()


# ── activation ───────────────────────────────────────────────────────────────


async def test_a_quiz_answered_in_a_started_lesson_within_a_week_activates(
    db: AsyncSession,
) -> None:
    signed_up = NOW - timedelta(days=10)
    user = await make_user(db, signed_up)
    session = await lesson(db, user, signed_up + timedelta(hours=1))
    db.add(showing(user, session, signed_up + timedelta(days=2), score=0.0))
    await db.flush()

    # A wrong answer still activates: the learner did the graded thing.
    assert await activated_at(db, user) == signed_up + timedelta(days=2)


async def test_the_professors_reading_of_a_chat_line_does_not_activate(
    db: AsyncSession,
) -> None:
    signed_up = NOW - timedelta(days=10)
    user = await make_user(db, signed_up)
    session = await lesson(db, user, signed_up)
    db.add(showing(user, session, signed_up + timedelta(hours=1), kind="conversation"))
    await db.flush()

    assert await activated_at(db, user) is None


async def test_a_graded_answer_after_seven_days_does_not_activate(
    db: AsyncSession,
) -> None:
    signed_up = NOW - timedelta(days=20)
    user = await make_user(db, signed_up)
    session = await lesson(db, user, signed_up)
    db.add(showing(user, session, signed_up + timedelta(days=7, minutes=1)))
    await db.flush()

    assert await activated_at(db, user) is None


async def test_a_lesson_the_learner_never_spoke_in_was_not_started(
    db: AsyncSession,
) -> None:
    signed_up = NOW - timedelta(days=10)
    user = await make_user(db, signed_up)
    session = await lesson(db, user, signed_up, learner_turn=False)
    db.add(showing(user, session, signed_up + timedelta(hours=1)))
    await db.flush()

    assert await activated_at(db, user) is None


async def test_a_flashcard_counts_against_its_lessons_journey(db: AsyncSession) -> None:
    """Flashcard showings carry no session id; the journey ties them to it."""
    signed_up = NOW - timedelta(days=10)
    user = await make_user(db, signed_up)
    session = await lesson(db, user, signed_up)
    db.add(
        showing(
            user,
            session,
            signed_up + timedelta(days=1),
            kind="flashcard",
            in_session=False,
        )
    )
    await db.flush()

    assert await activated_at(db, user) is not None


# ── successful sessions ──────────────────────────────────────────────────────


async def successes(db: AsyncSession, user: User) -> list[str]:
    rows = d.successful_sessions(*WINDOW).subquery()
    query = select(rows.c.kind).where(rows.c.owner_id == user.id)
    found: list[str] = list((await db.scalars(query)).all())
    return sorted(found)


async def test_a_lesson_succeeds_once_with_a_showing_at_or_above_point_six(
    db: AsyncSession,
) -> None:
    user = await make_user(db, NOW - timedelta(days=5))
    good = await lesson(db, user, NOW - timedelta(days=2))
    weak = await lesson(db, user, NOW - timedelta(days=2))
    db.add_all(
        [
            showing(user, good, NOW - timedelta(days=2), score=0.6),
            showing(user, good, NOW - timedelta(days=1), score=0.9),
            showing(user, weak, NOW - timedelta(days=2), score=0.59),
        ]
    )
    await db.flush()

    assert await successes(db, user) == [d.SESSION_TEACHING]


async def test_a_completed_focus_session_succeeds_and_an_abandoned_one_does_not(
    db: AsyncSession,
) -> None:
    user = await make_user(db, NOW - timedelta(days=5))
    for status, completed in (
        ("completed", NOW - timedelta(days=1)),
        ("abandoned", None),
    ):
        db.add(
            FocusSession(
                owner_id=user.id,
                kind="review",
                planned_minutes=10,
                steps_total=5,
                status=status,
                started_at=NOW - timedelta(days=1, minutes=10),
                completed_at=completed,
                last_activity_at=NOW - timedelta(days=1),
            )
        )
    await db.flush()

    assert await successes(db, user) == [d.SESSION_FOCUS]


async def test_a_review_session_needs_five_cards_on_one_day(db: AsyncSession) -> None:
    user = await make_user(db, NOW - timedelta(days=5))
    deck = await cards(db, user, 9)
    await rate(db, user, deck[:5], NOW - timedelta(days=2))
    await rate(db, user, deck[5:], NOW - timedelta(days=1))  # only four

    assert await successes(db, user) == [d.SESSION_REVIEW]


# ── the dashboard ────────────────────────────────────────────────────────────


async def test_the_report_counts_the_funnel_from_the_rows(db: AsyncSession) -> None:
    # Activated: signed up 10 days ago, quiz the same day, back the next day.
    a = await make_user(db, NOW - timedelta(days=10))
    session = await lesson(db, a, NOW - timedelta(days=10))
    db.add(showing(a, session, NOW - timedelta(days=10), score=0.8))
    db.add(
        TeachingTurn(
            owner_id=a.id,
            session_id=session.id,
            role=TurnRole.LEARNER,
            content="de novo",
            created_at=NOW - timedelta(days=9),
        )
    )
    # Signed up 10 days ago and never came back.
    await make_user(db, NOW - timedelta(days=10))
    # Signed up today, active today, paying through Stripe.
    c = await make_user(db, NOW, plan=Plan.PRO, stripe_customer_id="cus_test")
    db.add(
        LearningLifecycleEvent(
            owner_id=c.id,
            kind="lesson_started",
            source_id="s1",
            created_at=NOW,
        )
    )
    # A paid plan set by hand is not revenue.
    await make_user(db, NOW - timedelta(days=40), plan=Plan.STUDENT)
    await db.flush()

    report = await build_launch_report(db, days=30, now=NOW)

    assert report.signups == 3
    assert report.activation_cohort == 2
    assert report.activation_cohort_activated == 1
    assert report.activation_rate == 0.5
    assert report.dau == 1
    assert report.wau == 1
    assert report.lessons_started == 1
    assert report.successful_sessions[d.SESSION_TEACHING] == 1
    assert report.d1_cohort == 2 and report.d1_retained == 1
    assert report.d7_cohort == 2 and report.d7_retained == 0
    assert len(report.daily) == 30 and report.daily[-1].day == NOW.date()

    pro_price = await db.scalar(
        select(PlanConfig.monthly_price_cents).where(PlanConfig.plan == Plan.PRO)
    )
    pro = next(r for r in report.revenue if r.plan == "pro")
    student = next(r for r in report.revenue if r.plan == "student")
    assert pro.paying == 1 and pro.mrr_cents == (pro_price or 0)
    assert student.paying == 0 and student.comped == 1
    assert report.mrr_cents == (pro_price or 0)
    assert report.ai_latency_p50_ms is None and "ai_latency_ms" in report.not_recorded


async def test_an_empty_window_divides_by_nothing(db: AsyncSession) -> None:
    report = await build_launch_report(db, days=7, now=NOW + timedelta(days=3650))

    assert report.signups == 0
    assert report.activation_rate is None
    assert report.north_star is None
    assert report.d1_rate is None


# ── the route ────────────────────────────────────────────────────────────────


async def client_for(
    db: AsyncSession, user: User, settings: Settings
) -> httpx.AsyncClient:
    issued = await AuthService(db, settings).issue_session(user)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={deps.SESSION_COOKIE: issued.refresh_token},
        headers={deps.CSRF_HEADER: issued.csrf_token},
    )


@pytest.fixture
async def wired(db: AsyncSession, user: User) -> AsyncIterator[Settings]:
    settings = get_settings().model_copy(update={"noema_admin_emails": user.email})

    async def same_session() -> AsyncIterator[AsyncSession]:
        yield db

    app.dependency_overrides[get_session] = same_session
    app.dependency_overrides[get_settings] = lambda: settings
    redis = getattr(app.state, "redis", None)
    app.state.redis = None
    try:
        yield settings
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_settings, None)
        app.state.redis = redis


async def test_the_route_turns_away_anyone_not_an_admin(
    db: AsyncSession, other_user: User, wired: Settings
) -> None:
    async with await client_for(db, other_user, wired) as client:
        response = await client.get("/api/v1/admin/launch")
    assert response.status_code in (403, 404)


async def test_the_route_answers_an_admin_in_the_published_shape(
    db: AsyncSession, user: User, wired: Settings
) -> None:
    mfa = MfaService(db, SecretBox(os.urandom(32)))
    setup = await mfa.begin(user)
    await mfa.confirm(user, totp.code_at(setup.secret, time.time()))

    async with await client_for(db, user, wired) as client:
        response = await client.get("/api/v1/admin/launch", params={"days": 14})
        too_short = await client.get("/api/v1/admin/launch", params={"days": 3})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["days"] == 14 and len(body["daily"]) == 14
    assert set(body["successful_sessions"]) == {"teaching", "focus", "review"}
    assert "activation" in body["definitions"] and "north_star" in body["definitions"]
    assert body["ai_latency_p50_ms"] is None
    assert too_short.status_code == 422


# ── signup attribution ───────────────────────────────────────────────────────


def test_attribution_keeps_the_four_utm_tags_short_and_drops_the_rest() -> None:
    sent = RegisterRequest.model_validate(
        {
            "email": "a@example.com",
            "password": "correct-horse-battery",
            "display_name": "A",
            "attribution": {
                "utm_source": "  newsletter ",
                "utm_campaign": "x" * 500,
                "utm_medium": "",
                "gclid": "tracking-id",
            },
        }
    )
    assert sent.attribution is not None
    assert sent.attribution.cleaned() == {
        "utm_source": "newsletter",
        "utm_campaign": "x" * 100,
    }
    assert SignupAttribution().cleaned() is None


async def test_registration_stores_the_attribution_on_the_account(
    db: AsyncSession, settings: Settings
) -> None:
    user = await AuthService(db, settings).register(
        "tagged@example.com",
        "correct-horse-battery",
        "Tagged",
        attribution={"utm_source": "instagram", "utm_medium": "social"},
    )
    assert user.signup_attribution == {"utm_source": "instagram", "utm_medium": "social"}
