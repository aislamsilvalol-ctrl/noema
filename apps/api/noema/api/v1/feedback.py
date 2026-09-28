"""Report a problem, send an idea: the one channel that is not a thumbs-up."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from noema.api.v1 import deps
from noema.api.v1.schemas import FeedbackIn
from noema.services.feedback import FeedbackService

router = APIRouter(
    prefix="/feedback", tags=["feedback"], dependencies=[Depends(deps.require_csrf)]
)


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
async def send_feedback(
    payload: FeedbackIn,
    request: Request,
    user: deps.CurrentUser,
    db: deps.SessionDep,
) -> None:
    """A bug, a confusion, a bad reply or an idea, in the learner's words.

    The browser string comes from the request, not the body: it is context
    for reproducing a bug, and the client has no reason to choose it.
    """
    await FeedbackService(db).report(
        user.id,
        kind=payload.kind,
        message=payload.message,
        page=payload.page,
        user_agent=request.headers.get("user-agent"),
    )
