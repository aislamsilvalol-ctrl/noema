"""Evaluating the scheduler against what actually happened.

Two questions, both answerable only because the evidence log is append-only:

* is the memory model calibrated — does predicted recall match observed recall?
* is the planner calibrated — does a session take as long as it said it would?

Neither is a vanity metric. The first decides whether the intervals are honest; the
second decides whether "you have 30 minutes" means anything.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.db.models import Review, StudySession
from noema.engines import fsrs
from noema.engines.replay import Attempt, ReplayResult, compare, replay

__all__ = [
    "PlannerCalibration",
    "evaluate_memory_model",
    "evaluate_planner",
    "try_weights",
]

#: Below this, the numbers are noise. `docs/fsrs.md` uses the same threshold before
#: fitting personal weights, for the same reason.
MIN_REVIEWS = 50


@dataclass(frozen=True, slots=True)
class PlannerCalibration:
    sessions: int
    mean_estimated_minutes: float
    mean_actual_minutes: float
    completion_rate: float

    @property
    def overestimates(self) -> bool:
        return self.mean_estimated_minutes > self.mean_actual_minutes

    def summary(self) -> str:
        if self.sessions == 0:
            return "No completed sessions yet."
        gap = abs(self.mean_estimated_minutes - self.mean_actual_minutes)
        if gap < 1:
            return f"Session estimates are accurate across {self.sessions} sessions."
        direction = "over" if self.overestimates else "under"
        return (
            f"Sessions run {gap:.0f} min {direction} the estimate, "
            f"across {self.sessions} sessions."
        )


async def evaluate_memory_model(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    weights: fsrs.Weights = fsrs.DEFAULT_WEIGHTS,
) -> ReplayResult:
    """Replay this learner's whole review history and score the predictions."""
    return replay(await _attempts(session, owner_id), weights=weights)


async def try_weights(
    session: AsyncSession, *, owner_id: uuid.UUID, candidate: fsrs.Weights
) -> tuple[ReplayResult, ReplayResult, bool]:
    """Score a candidate weight set against the current one on real history.

    This is what makes changing the scheduler an experiment rather than an opinion.
    """
    return compare(await _attempts(session, owner_id), candidate=candidate)


async def evaluate_planner(
    session: AsyncSession, *, owner_id: uuid.UUID, days: int = 90
) -> PlannerCalibration:
    """How close the planned minutes came to the minutes actually spent."""
    since = datetime.now(UTC) - timedelta(days=days)

    row = (
        await session.execute(
            select(
                func.count(),
                func.avg(StudySession.estimated_seconds),
                func.avg(StudySession.actual_seconds),
                func.sum(StudySession.items_completed),
                func.sum(StudySession.items_planned),
            ).where(
                StudySession.owner_id == owner_id,
                StudySession.completed_at.is_not(None),
                StudySession.started_at >= since,
            )
        )
    ).one()

    count, estimated, actual, completed, planned = row
    if not count:
        return PlannerCalibration(0, 0.0, 0.0, 0.0)

    return PlannerCalibration(
        sessions=int(count),
        mean_estimated_minutes=round(float(estimated or 0) / 60, 1),
        mean_actual_minutes=round(float(actual or 0) / 60, 1),
        completion_rate=round(float(completed or 0) / float(planned or 1), 3),
    )


async def _attempts(session: AsyncSession, owner_id: uuid.UUID) -> list[Attempt]:
    """The review log, as the replay wants it.

    ``elapsed_days`` is reconstructed from consecutive reviews of the same card
    rather than stored, so the history replays exactly as it was experienced.
    """
    rows = (
        await session.execute(
            select(Review.card_id, Review.rating, Review.reviewed_at)
            .where(Review.owner_id == owner_id)
            .order_by(Review.reviewed_at)
        )
    ).all()

    previous: dict[uuid.UUID, datetime] = {}
    attempts: list[Attempt] = []

    for card_id, rating, reviewed_at in rows:
        moment = reviewed_at if reviewed_at.tzinfo else reviewed_at.replace(tzinfo=UTC)
        last = previous.get(card_id)
        elapsed = (moment - last).total_seconds() / 86400 if last else 0.0
        previous[card_id] = moment

        attempts.append(
            Attempt(
                card_id=str(card_id),
                elapsed_days=max(elapsed, 0.0),
                rating=fsrs.Rating(int(rating)),
            )
        )

    return attempts


def has_enough_history(result: ReplayResult) -> bool:
    return result.attempts >= MIN_REVIEWS
