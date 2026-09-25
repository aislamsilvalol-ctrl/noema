"""Account progress: level, today's missions, marks.

The server decides every number here from the learning evidence; the client
sends only its time zone, which moves the day's boundaries and nothing else.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from noema.api.v1 import deps
from noema.api.v1.schemas import MarkOut, MissionOut, ProgressionOut
from noema.services.progression import ProgressionEngine

router = APIRouter(prefix="/me/progress", tags=["progression"])


@router.get("", response_model=ProgressionOut)
async def progress(
    user: deps.CurrentUser,
    db: deps.SessionDep,
    tz: str = Query(default="UTC", max_length=64),
) -> ProgressionOut:
    engine = ProgressionEngine(db, user.id, tz)
    await engine.sync()
    summary = await engine.summary()
    return ProgressionOut(
        level=summary.level,
        stage=summary.stage,
        xp_total=summary.xp_total,
        level_floor=summary.level_floor,
        next_level_at=summary.next_level_at,
        xp_today=summary.xp_today,
        missions=[
            MissionOut(
                id=m.id,
                period=m.period,
                progress=m.progress,
                target=m.target,
                done=m.done,
                xp=m.xp,
                ends_at=m.ends_at,
            )
            for m in summary.missions
        ],
        marks=[
            MarkOut(id=m.id, earned=m.earned, earned_at=m.earned_at)
            for m in summary.marks
        ],
    )
