"""Sending material back out, in a format that needs no plugin to open.

The mirror of `noema.api.v1.imports`: whatever a learner brought in from Anki,
or built here, leaves the same way.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response

from noema.api.v1 import deps
from noema.core.logging import get_logger
from noema.db.base import utcnow
from noema.services.exports import export_anki, export_markdown

log = get_logger(__name__)

router = APIRouter(
    prefix="/exports", tags=["exports"], dependencies=[Depends(deps.require_csrf)]
)


@router.get("/anki")
async def export_anki_package(
    user: deps.CurrentUser, db: deps.SessionDep, notebook_id: uuid.UUID
) -> Response:
    """Every studyable card in a notebook, as a `.apkg` with its review history."""
    report = await export_anki(db, owner_id=user.id, notebook_id=notebook_id)
    filename = f"noema-export-{utcnow():%Y-%m-%d}.apkg"

    log.info(
        "anki.exported",
        user_id=str(user.id),
        notebook_id=str(notebook_id),
        exported=report.exported,
        scheduled=report.scheduled,
        skipped=dict(report.skipped),
    )
    return Response(
        content=report.data,
        media_type="application/octet-stream",
        headers={"content-disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/markdown")
async def export_markdown_package(
    user: deps.CurrentUser, db: deps.SessionDep, notebook_id: uuid.UUID
) -> Response:
    """Every note in a notebook, as a zip of Markdown files readable anywhere."""
    data = await export_markdown(db, owner_id=user.id, notebook_id=notebook_id)
    filename = f"noema-export-{utcnow():%Y-%m-%d}.zip"

    log.info("markdown.exported", user_id=str(user.id), notebook_id=str(notebook_id))
    return Response(
        content=data,
        media_type="application/zip",
        headers={"content-disposition": f'attachment; filename="{filename}"'},
    )
