"""What "active", "activated" and "a successful session" mean, in one place.

The launch dashboard (`noema.services.launch_dashboard`) and any later job
that reports these numbers read them from here, so the definition and the
query cannot drift apart. Every definition is computed from the database,
never from Plausible: the browser's events are for the top of the funnel and
for attribution, and a blocked script must not change who counts as activated.

All days are UTC calendar days. See ``docs/analytics.md`` for the reasoning.

**Active learner** (DAU/WAU): someone with, that day or week, a lifecycle fact
in ``learning_events``, a learner turn in a lesson, or a rated review card.

**Activated**: an account that, within 7 days of signing up, answered at least
one graded item (quiz, check, assessment, teach-back, flashcard -- every
``mastery_events`` kind except the professor's own reading of a chat line) in
a lesson they started (a teaching session with at least one learner turn).
Flashcard events carry no session, so they count against the lesson's journey.

**Successful learning session**, one of:

* a teaching session with at least one ``mastery_events`` row scoring ≥ 0.6,
  dated by its first such row;
* a Modo TDAH focus session completed, dated by ``completed_at``;
* a review session with at least 5 rated cards, where a review session is one
  learner's reviews on one UTC day (reviews carry no session id), dated by the
  first of them.

**North Star**: successful learning sessions per weekly active learner.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import (
    Date,
    Select,
    and_,
    cast,
    func,
    literal,
    or_,
    select,
    union,
    union_all,
)
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import CompoundSelect

from noema.db.models import (
    FocusSession,
    FocusStatus,
    LearningLifecycleEvent,
    MasteryEvent,
    Review,
    TeachingSession,
    TeachingTurn,
    TurnRole,
    User,
)

ACTIVATION_WINDOW = timedelta(days=7)
#: Graded showings. ``conversation`` (the professor reading a chat line) is
#: the one kind a learner did not answer, so it cannot activate anyone.
GRADED_MASTERY_KINDS = ("quiz", "check", "assessment", "teach_back", "flashcard")
SUCCESS_MASTERY_SCORE = 0.6
REVIEW_SESSION_MIN_CARDS = 5

SESSION_TEACHING = "teaching"
SESSION_FOCUS = "focus"
SESSION_REVIEW = "review"

#: Plain-language copies, returned with the dashboard so nobody reads a number
#: without its definition.
DEFINITIONS = {
    "active_learner": (
        "Someone with a lesson event, a learner turn or a rated review card "
        "that UTC day (DAU) or week (WAU)."
    ),
    "activation": (
        "Within 7 days of signup: started a lesson and answered at least one "
        "graded item in it (quiz, check, assessment, teach-back or flashcard)."
    ),
    "successful_session": (
        "A lesson with a graded showing scoring ≥ 0.6, a completed focus "
        "session, or a day's review of ≥ 5 cards."
    ),
    "north_star": "Successful learning sessions per weekly active learner.",
}


def utc_day(column: Any) -> ColumnElement[date]:
    """The UTC calendar day of a timestamptz, whatever the session TimeZone."""
    return cast(func.timezone("UTC", column), Date)


def active_learner_rows(start: datetime, end: datetime) -> CompoundSelect[Any]:
    """``(owner_id, at)`` for every act that makes someone active in [start, end).

    A ``UNION`` of three indexed range scans; callers group it by day or week.
    """
    return union_all(
        select(
            LearningLifecycleEvent.owner_id.label("owner_id"),
            LearningLifecycleEvent.created_at.label("at"),
        ).where(
            LearningLifecycleEvent.created_at >= start,
            LearningLifecycleEvent.created_at < end,
        ),
        select(
            TeachingTurn.owner_id.label("owner_id"),
            TeachingTurn.created_at.label("at"),
        ).where(
            TeachingTurn.role == TurnRole.LEARNER,
            TeachingTurn.created_at >= start,
            TeachingTurn.created_at < end,
        ),
        select(
            Review.owner_id.label("owner_id"),
            Review.reviewed_at.label("at"),
        ).where(Review.reviewed_at >= start, Review.reviewed_at < end),
    )


def active_learner_days(start: datetime, end: datetime) -> CompoundSelect[Any]:
    """Distinct ``(owner_id, day)`` pairs: one row per learner per active day."""
    rows = active_learner_rows(start, end).subquery()
    return union(select(rows.c.owner_id, utc_day(rows.c.at).label("day")))


def activations(signed_up_from: datetime, signed_up_to: datetime) -> Select[Any]:
    """``(user_id, signed_up_at, activated_at)`` for every account created in
    [signed_up_from, signed_up_to); ``activated_at`` is null when not activated.
    """
    lesson_started = (
        select(TeachingTurn.id)
        .where(
            TeachingTurn.session_id == TeachingSession.id,
            TeachingTurn.role == TurnRole.LEARNER,
        )
        .exists()
    )
    graded = (
        select(
            MasteryEvent.owner_id.label("owner_id"),
            func.min(MasteryEvent.created_at).label("activated_at"),
        )
        .join(User, User.id == MasteryEvent.owner_id)
        .join(
            TeachingSession,
            and_(
                TeachingSession.owner_id == MasteryEvent.owner_id,
                or_(
                    MasteryEvent.session_id == TeachingSession.id,
                    and_(
                        MasteryEvent.session_id.is_(None),
                        MasteryEvent.journey_id == TeachingSession.journey_id,
                    ),
                ),
            ),
        )
        .where(
            User.created_at >= signed_up_from,
            User.created_at < signed_up_to,
            MasteryEvent.kind.in_(GRADED_MASTERY_KINDS),
            MasteryEvent.created_at >= User.created_at,
            MasteryEvent.created_at < User.created_at + ACTIVATION_WINDOW,
            lesson_started,
        )
        .group_by(MasteryEvent.owner_id)
        .subquery()
    )
    return (
        select(
            User.id.label("user_id"),
            User.created_at.label("signed_up_at"),
            graded.c.activated_at,
        )
        .outerjoin(graded, graded.c.owner_id == User.id)
        .where(User.created_at >= signed_up_from, User.created_at < signed_up_to)
    )


def successful_sessions(start: datetime, end: datetime) -> CompoundSelect[Any]:
    """``(owner_id, kind, occurred_at)``, one row per successful session whose
    date falls in [start, end). A lesson is counted once, on the day it first
    succeeded, however long it runs."""
    teaching = (
        select(
            MasteryEvent.owner_id.label("owner_id"),
            literal(SESSION_TEACHING).label("kind"),
            func.min(MasteryEvent.created_at).label("occurred_at"),
        )
        .where(
            MasteryEvent.session_id.is_not(None),
            MasteryEvent.score >= SUCCESS_MASTERY_SCORE,
            MasteryEvent.created_at < end,
        )
        .group_by(MasteryEvent.owner_id, MasteryEvent.session_id)
        .having(func.min(MasteryEvent.created_at) >= start)
    )
    focus = select(
        FocusSession.owner_id.label("owner_id"),
        literal(SESSION_FOCUS).label("kind"),
        FocusSession.completed_at.label("occurred_at"),
    ).where(
        FocusSession.status == FocusStatus.COMPLETED.value,
        FocusSession.completed_at >= start,
        FocusSession.completed_at < end,
    )
    review = (
        select(
            Review.owner_id.label("owner_id"),
            literal(SESSION_REVIEW).label("kind"),
            func.min(Review.reviewed_at).label("occurred_at"),
        )
        .where(Review.reviewed_at >= start, Review.reviewed_at < end)
        .group_by(Review.owner_id, utc_day(Review.reviewed_at))
        .having(func.count() >= REVIEW_SESSION_MIN_CARDS)
    )
    return union_all(teaching, focus, review)
