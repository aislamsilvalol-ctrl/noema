"""Taking your data out, and taking it away.

The README promises both. Neither is a support ticket, and neither is a feature that
can be added later without the promise having been false in the meantime.

Export produces an archive that is useful without NOEMA: notes as Markdown files you
can open anywhere, the original uploads exactly as they were given to us, and the
derived structure as JSON for anyone who wants it. An export that only another copy
of NOEMA can read is a lock-in with extra steps.
"""

from __future__ import annotations

import io
import json
import re
import uuid
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.logging import get_logger
from noema.db.base import utcnow
from noema.db.models import (
    Card,
    Concept,
    ConceptEdge,
    ConceptMastery,
    Note,
    Notebook,
    Question,
    Session,
    Source,
    Subject,
    User,
    Workspace,
)
from noema.ingestion.storage import Storage, StorageError

log = get_logger(__name__)

__all__ = [
    "DeletionRequest",
    "build_export",
    "purge_expired_accounts",
    "request_deletion",
]

#: How long a deleted account is recoverable. Long enough to undo a mistake made at
#: 2am, short enough that "deleted" means something.
GRACE_DAYS = 30

UNSAFE_PATH = re.compile(r"[^\w\- ]+")


@dataclass(frozen=True, slots=True)
class DeletionRequest:
    user_id: uuid.UUID
    requested_at: datetime
    purge_after: datetime


async def build_export(
    session: AsyncSession, user: User, *, storage: Storage | None = None
) -> bytes:
    """Everything this account owns, as a zip.

    Built in memory. A learner's library is measured in tens of megabytes; streaming
    would add complexity for a case that does not exist yet, and the size cap on
    uploads bounds it.
    """
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.md", _readme(user))
        archive.writestr(
            "account.json",
            _dump(
                {
                    "email": user.email,
                    "display_name": user.display_name,
                    "created_at": user.created_at,
                    "exported_at": utcnow(),
                    "settings": user.settings,
                }
            ),
        )

        notebooks = await _notebooks(session, user.id)
        archive.writestr("library.json", _dump(await _library(session, user.id)))
        archive.writestr("knowledge.json", _dump(await _knowledge(session, user.id)))
        archive.writestr("study.json", _dump(await _study(session, user.id)))

        await _write_notes(session, archive, user.id, notebooks)
        if storage is not None:
            await _write_sources(session, archive, user.id, storage)
            await _write_card_images(session, archive, user.id, storage)

    return buffer.getvalue()


async def request_deletion(session: AsyncSession, user: User) -> DeletionRequest:
    """Mark an account for deletion and lock it immediately.

    Sessions are revoked now rather than in 30 days: someone who asked to be deleted
    should not stay logged in, and a grace period is for recovering the data, not
    for continuing to use the account.
    """
    now = utcnow()
    user.deleted_at = now

    await session.execute(
        update(Session)
        .where(Session.user_id == user.id, Session.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await session.flush()

    log.info("account.deletion_requested", user_id=str(user.id))
    return DeletionRequest(
        user_id=user.id, requested_at=now, purge_after=now + timedelta(days=GRACE_DAYS)
    )


async def purge_expired_accounts(
    session: AsyncSession, *, storage: Storage | None = None, now: datetime | None = None
) -> list[uuid.UUID]:
    """Permanently remove accounts past their grace period.

    Rows cascade from ``users``. Stored files do not, so they are deleted explicitly
    — an account purge that leaves someone's PDFs on disk has not deleted anything.
    """
    now = now or utcnow()
    cutoff = now - timedelta(days=GRACE_DAYS)

    expired = list(
        (
            await session.scalars(
                select(User.id).where(
                    User.deleted_at.is_not(None), User.deleted_at <= cutoff
                )
            )
        ).all()
    )
    if not expired:
        return []

    if storage is not None:
        source_keys = (
            await session.scalars(
                select(Source.storage_key).where(
                    Source.owner_id.in_(expired), Source.storage_key.is_not(None)
                )
            )
        ).all()
        card_image_keys = (
            await session.scalars(
                select(Card.front_image_key).where(
                    Card.owner_id.in_(expired), Card.front_image_key.is_not(None)
                )
            )
        ).all()
        for key in [*source_keys, *card_image_keys]:
            if key is None:
                continue
            try:
                await storage.delete(key)
            except StorageError as exc:
                # A missing file is fine; anything else must not stop the purge, or
                # one bad key keeps an account alive forever.
                log.warning("account.purge_file_failed", key=key, error=str(exc))

    await session.execute(delete(User).where(User.id.in_(expired)))
    await session.flush()

    log.info("account.purged", count=len(expired))
    return expired


async def _notebooks(session: AsyncSession, owner_id: uuid.UUID) -> dict[uuid.UUID, str]:
    rows = (
        await session.execute(
            select(Notebook.id, Notebook.title).where(
                Notebook.owner_id == owner_id, Notebook.deleted_at.is_(None)
            )
        )
    ).all()
    return {row.id: row.title for row in rows}


async def _library(session: AsyncSession, owner_id: uuid.UUID) -> dict[str, Any]:
    async def rows(model: Any, *columns: Any) -> list[dict[str, Any]]:
        result = await session.execute(select(*columns).where(model.owner_id == owner_id))
        return [dict(row._mapping) for row in result]

    return {
        "workspaces": await rows(
            Workspace, Workspace.id, Workspace.title, Workspace.slug
        ),
        "subjects": await rows(
            Subject, Subject.id, Subject.workspace_id, Subject.title, Subject.slug
        ),
        "notebooks": await rows(
            Notebook,
            Notebook.id,
            Notebook.subject_id,
            Notebook.title,
            Notebook.slug,
            Notebook.description,
        ),
        "sources": await rows(
            Source,
            Source.id,
            Source.notebook_id,
            Source.kind,
            Source.original_filename,
            Source.byte_size,
            Source.status,
        ),
    }


async def _knowledge(session: AsyncSession, owner_id: uuid.UUID) -> dict[str, Any]:
    concepts = (
        await session.execute(
            select(
                Concept.id,
                Concept.name,
                Concept.definition,
                Concept.status,
                Concept.difficulty_prior,
            ).where(Concept.owner_id == owner_id)
        )
    ).all()
    edges = (
        await session.execute(
            select(
                ConceptEdge.src_id,
                ConceptEdge.dst_id,
                ConceptEdge.kind,
                ConceptEdge.weight,
            ).where(ConceptEdge.owner_id == owner_id)
        )
    ).all()

    return {
        "concepts": [dict(row._mapping) for row in concepts],
        "edges": [dict(row._mapping) for row in edges],
    }


async def _study(session: AsyncSession, owner_id: uuid.UUID) -> dict[str, Any]:
    """Cards, questions and mastery — enough to rebuild a deck elsewhere."""
    cards = (
        await session.execute(
            select(
                Card.id,
                Card.notebook_id,
                Card.concept_id,
                Card.type,
                Card.front_md,
                Card.back_md,
            ).where(Card.owner_id == owner_id, Card.deleted_at.is_(None))
        )
    ).all()
    questions = (
        await session.execute(
            select(
                Question.id,
                Question.notebook_id,
                Question.concept_id,
                Question.type,
                Question.difficulty,
                Question.prompt,
                Question.payload,
            ).where(Question.owner_id == owner_id, Question.deleted_at.is_(None))
        )
    ).all()
    mastery = (
        await session.execute(
            select(
                ConceptMastery.concept_id,
                ConceptMastery.mastery,
                ConceptMastery.components,
            ).where(ConceptMastery.owner_id == owner_id)
        )
    ).all()

    return {
        "cards": [dict(row._mapping) for row in cards],
        "questions": [dict(row._mapping) for row in questions],
        "mastery": [dict(row._mapping) for row in mastery],
    }


async def _write_notes(
    session: AsyncSession,
    archive: zipfile.ZipFile,
    owner_id: uuid.UUID,
    notebooks: dict[uuid.UUID, str],
) -> None:
    """Notes as Markdown, in folders named after their notebook.

    Readable in any editor, which is the point of an export.
    """
    notes = (
        await session.scalars(
            select(Note).where(Note.owner_id == owner_id, Note.deleted_at.is_(None))
        )
    ).all()

    used: set[str] = set()
    for note in notes:
        folder = _safe(notebooks.get(note.notebook_id, "notebook"))
        path = f"notes/{folder}/{_safe(note.title)}.md"

        # Two notes can share a title; neither should overwrite the other.
        suffix = 1
        while path in used:
            suffix += 1
            path = f"notes/{folder}/{_safe(note.title)} ({suffix}).md"
        used.add(path)

        archive.writestr(path, f"# {note.title}\n\n{note.content_md}")


async def _write_sources(
    session: AsyncSession,
    archive: zipfile.ZipFile,
    owner_id: uuid.UUID,
    storage: Storage,
) -> None:
    """The original uploads, byte for byte."""
    sources = (
        await session.scalars(
            select(Source).where(
                Source.owner_id == owner_id,
                Source.deleted_at.is_(None),
                Source.storage_key.is_not(None),
            )
        )
    ).all()

    used: set[str] = set()
    for source in sources:
        if source.storage_key is None:
            continue
        try:
            data = await storage.get(source.storage_key)
        except StorageError as exc:
            # A missing file must not cost the learner the rest of their export.
            log.warning("export.source_missing", source_id=str(source.id), error=str(exc))
            continue

        name = _safe(source.original_filename or str(source.id))
        path = f"sources/{name}"
        suffix = 1
        while path in used:
            suffix += 1
            path = f"sources/{suffix}-{name}"
        used.add(path)

        archive.writestr(path, data)


async def _write_card_images(
    session: AsyncSession,
    archive: zipfile.ZipFile,
    owner_id: uuid.UUID,
    storage: Storage,
) -> None:
    """Images attached to image cards, byte for byte — same reasoning as sources."""
    cards = (
        await session.scalars(
            select(Card).where(
                Card.owner_id == owner_id,
                Card.deleted_at.is_(None),
                Card.front_image_key.is_not(None),
            )
        )
    ).all()

    for card in cards:
        if card.front_image_key is None:
            continue
        try:
            data = await storage.get(card.front_image_key)
        except StorageError as exc:
            log.warning("export.card_image_missing", card_id=str(card.id), error=str(exc))
            continue

        extension = card.front_image_key.rsplit(".", 1)[-1]
        archive.writestr(f"card-images/{card.id}.{extension}", data)


def _readme(user: User) -> str:
    return f"""# Your NOEMA export

Everything this account owns, as of {utcnow():%Y-%m-%d}.

- `notes/` — your notes as Markdown, grouped by notebook. Open them anywhere.
- `sources/` — the files you uploaded, unchanged.
- `card-images/` — images attached to your image cards, unchanged.
- `library.json` — workspaces, subjects, notebooks and source metadata.
- `knowledge.json` — extracted concepts and the edges between them.
- `study.json` — cards, questions and mastery scores.
- `account.json` — your account details.

Nothing here needs NOEMA to read. That is deliberate: an export only another copy of
the same software can open is not really your data.

Exported for {user.email}.
"""


def _dump(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, default=_encode)


def _encode(value: Any) -> str:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return str(value)


def _safe(name: str) -> str:
    """A filename that cannot escape its folder or break an unzipper."""
    cleaned = UNSAFE_PATH.sub("", name).strip() or "untitled"
    return cleaned[:80]


def sources_for(rows: Sequence[Source]) -> list[str]:
    return [row.storage_key for row in rows if row.storage_key]
