"""Modo TDAH: the next activity, and short focus sittings around it.

`GET /me/next-activity` is generic — one deterministic answer to "what now?"
that any screen can use. The `/focus/sessions` routes keep the shape of a
sitting (planned minutes, steps, paused or not) on the server, so a refresh
or another device resumes on the same step. The learning itself goes through
the ordinary endpoints (`/ai/professor`, `/reviews`), never through these.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, status

from noema.api.v1 import deps
from noema.api.v1.schemas import (
    FocusSessionOut,
    FocusStartIn,
    FocusStepIn,
    FocusSummaryOut,
    NextActivityOut,
)
from noema.db.base import utcnow
from noema.db.models import FocusSession, FocusStatus
from noema.services.focus_sessions import FocusSessions
from noema.services.next_activity import LEARN_MINUTES, next_activity

router = APIRouter(
    prefix="/focus", tags=["focus"], dependencies=[Depends(deps.require_csrf)]
)
activity_router = APIRouter(prefix="/me", tags=["focus"])


def _learn_minutes(settings: dict[str, object]) -> int:
    """The learner's own sitting length, when they set one; otherwise ours."""
    raw = settings.get("session_minutes")
    if isinstance(raw, int) and not isinstance(raw, bool):
        return max(5, min(25, raw))
    return LEARN_MINUTES


def seconds_left(row: FocusSession, now: datetime) -> int:
    end = row.completed_at or now
    paused = row.paused_seconds
    if row.paused_at is not None and row.completed_at is None:
        paused += max(0, int((now - row.paused_at).total_seconds()))
    spent = (end - row.started_at).total_seconds() - paused
    return int(row.planned_minutes * 60 - spent)


async def _out(service: FocusSessions, row: FocusSession) -> FocusSessionOut:
    now = utcnow()
    summary = await service.summary(row, now=now)
    return FocusSessionOut(
        id=row.id,
        kind=cast(Any, row.kind),
        title=row.title,
        concept=row.concept,
        journey_id=row.journey_id,
        teaching_session_id=row.teaching_session_id,
        planned_minutes=row.planned_minutes,
        steps_total=row.steps_total,
        steps_done=row.steps_done,
        status=cast(Any, row.status),
        started_at=row.started_at,
        paused_at=row.paused_at,
        completed_at=row.completed_at,
        last_activity_at=row.last_activity_at,
        seconds_left=seconds_left(row, now),
        summary=FocusSummaryOut(
            cards_reviewed=summary.cards_reviewed,
            concepts_touched=summary.concepts_touched,
        ),
    )


@activity_router.get("/next-activity", response_model=NextActivityOut)
async def get_next_activity(
    user: deps.CurrentUser, db: deps.SessionDep
) -> NextActivityOut:
    activity = await next_activity(
        db, user.id, learn_minutes=_learn_minutes(user.settings or {})
    )
    return NextActivityOut.model_validate(activity.public())


@router.post(
    "/sessions", response_model=FocusSessionOut, status_code=status.HTTP_201_CREATED
)
async def start_focus_session(
    payload: FocusStartIn, user: deps.CurrentUser, db: deps.SessionDep
) -> FocusSessionOut:
    """Start a sitting from the next activity — or return the one under way."""
    service = FocusSessions(db, user.id)
    row = await service.start(
        minutes=payload.minutes,
        goal=payload.goal,
        learn_minutes=_learn_minutes(user.settings or {}),
    )
    return await _out(service, row)


@router.get("/sessions/current", response_model=FocusSessionOut | None)
async def current_focus_session(
    user: deps.CurrentUser, db: deps.SessionDep
) -> FocusSessionOut | None:
    service = FocusSessions(db, user.id)
    row = await service.current()
    return None if row is None else await _out(service, row)


@router.get("/sessions/{focus_id}", response_model=FocusSessionOut)
async def get_focus_session(
    focus_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> FocusSessionOut:
    service = FocusSessions(db, user.id)
    return await _out(service, await service.get(focus_id))


@router.post("/sessions/{focus_id}/step", response_model=FocusSessionOut)
async def focus_step(
    focus_id: uuid.UUID,
    payload: FocusStepIn,
    user: deps.CurrentUser,
    db: deps.SessionDep,
) -> FocusSessionOut:
    service = FocusSessions(db, user.id)
    return await _out(service, await service.step(focus_id, index=payload.index))


@router.post("/sessions/{focus_id}/pause", response_model=FocusSessionOut)
async def pause_focus_session(
    focus_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> FocusSessionOut:
    service = FocusSessions(db, user.id)
    return await _out(service, await service.pause(focus_id))


@router.post("/sessions/{focus_id}/resume", response_model=FocusSessionOut)
async def resume_focus_session(
    focus_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> FocusSessionOut:
    service = FocusSessions(db, user.id)
    return await _out(service, await service.resume(focus_id))


@router.post("/sessions/{focus_id}/complete", response_model=FocusSessionOut)
async def complete_focus_session(
    focus_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> FocusSessionOut:
    service = FocusSessions(db, user.id)
    row = await service.finish(focus_id, status=FocusStatus.COMPLETED)
    return await _out(service, row)


@router.post("/sessions/{focus_id}/abandon", response_model=FocusSessionOut)
async def abandon_focus_session(
    focus_id: uuid.UUID, user: deps.CurrentUser, db: deps.SessionDep
) -> FocusSessionOut:
    service = FocusSessions(db, user.id)
    row = await service.finish(focus_id, status=FocusStatus.ABANDONED)
    return await _out(service, row)
