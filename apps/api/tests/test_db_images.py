"""Image flashcards, against a real database and real storage.

Called directly as plain coroutines rather than through an HTTP client — the
same convention every other `noema.api.v1.*` test in this suite follows for
"study" routes, since none of them go through FastAPI's dependency injection
either. What's under test is real: multipart-style upload validation, the
stored bytes round-tripping through `Storage`, and tenancy on both the upload
and the serving side.
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path

import pytest
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from noema.api.v1.study import create_image_card, get_card_image
from noema.core.config import Settings
from noema.core.errors import NotFound
from noema.db.models import Card, CardType, Notebook, Subject, User, Workspace
from noema.db.repository import OwnedRepository
from noema.ingestion.images import ImageTooLarge, RejectedImage
from noema.ingestion.storage import build_storage

pytestmark = pytest.mark.asyncio

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture
async def notebook(db: AsyncSession, user: User) -> Notebook:
    workspace = await OwnedRepository(db, Workspace, user.id).create(
        title="Bio", slug=f"bio-{uuid.uuid4().hex[:8]}"
    )
    subject = await OwnedRepository(db, Subject, user.id).create(
        workspace_id=workspace.id, title="Cells", slug=f"cells-{uuid.uuid4().hex[:8]}"
    )
    return await OwnedRepository(db, Notebook, user.id).create(
        subject_id=subject.id,
        title="Organelles",
        slug=f"org-{uuid.uuid4().hex[:8]}",
        retrieval_settings={},
    )


@pytest.fixture(autouse=True)
def _local_storage(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The default storage path isn't writable outside a real deployment."""
    monkeypatch.setattr(settings, "storage_local_path", str(tmp_path))


def upload_file(data: bytes = PNG, filename: str = "diagram.png") -> UploadFile:
    return UploadFile(io.BytesIO(data), filename=filename)


async def test_uploading_an_image_creates_an_image_card_with_the_bytes_stored(
    db: AsyncSession, user: User, notebook: Notebook, settings: Settings
) -> None:
    out = await create_image_card(
        user=user,
        db=db,
        settings=settings,
        notebook_id=notebook.id,
        front_md="What is labeled A?",
        back_md="The mitochondria.",
        concept_id=None,
        image=upload_file(),
    )

    assert out.type is CardType.IMAGE
    assert out.has_image is True
    assert out.front_md == "What is labeled A?"

    card = await db.get(Card, out.id)
    assert card is not None
    assert card.front_image_key is not None
    stored = await build_storage(settings).get(card.front_image_key)
    assert stored == PNG


async def test_the_stored_bytes_round_trip_through_storage(
    db: AsyncSession, user: User, notebook: Notebook, settings: Settings
) -> None:
    out = await create_image_card(
        user=user,
        db=db,
        settings=settings,
        notebook_id=notebook.id,
        front_md="What is labeled A?",
        back_md="The mitochondria.",
        concept_id=None,
        image=upload_file(),
    )

    response = await get_card_image(card_id=out.id, user=user, db=db, settings=settings)

    assert response.body == PNG
    assert response.media_type == "image/png"


async def test_a_card_with_no_image_is_not_found_on_the_image_route(
    db: AsyncSession, user: User, notebook: Notebook, settings: Settings
) -> None:
    from noema.api.v1.study import CardCreate, create_card

    card = await create_card(
        CardCreate(notebook_id=notebook.id, front_md="Q", back_md="A"),
        user=user,
        db=db,
    )

    with pytest.raises(NotFound):
        await get_card_image(card_id=card.id, user=user, db=db, settings=settings)


async def test_a_nonexistent_card_is_not_found_on_the_image_route(
    db: AsyncSession, user: User, settings: Settings
) -> None:
    with pytest.raises(NotFound):
        await get_card_image(card_id=uuid.uuid4(), user=user, db=db, settings=settings)


async def test_another_owners_image_card_is_not_reachable(
    db: AsyncSession,
    user: User,
    other_user: User,
    notebook: Notebook,
    settings: Settings,
) -> None:
    out = await create_image_card(
        user=user,
        db=db,
        settings=settings,
        notebook_id=notebook.id,
        front_md="What is labeled A?",
        back_md="The mitochondria.",
        concept_id=None,
        image=upload_file(),
    )

    with pytest.raises(NotFound):
        await get_card_image(card_id=out.id, user=other_user, db=db, settings=settings)


async def test_non_image_data_is_rejected(
    db: AsyncSession, user: User, notebook: Notebook, settings: Settings
) -> None:
    with pytest.raises(RejectedImage):
        await create_image_card(
            user=user,
            db=db,
            settings=settings,
            notebook_id=notebook.id,
            front_md="What is labeled A?",
            back_md="The mitochondria.",
            concept_id=None,
            image=upload_file(b"not an image", filename="diagram.png"),
        )


async def test_an_oversized_image_is_rejected(
    db: AsyncSession, user: User, notebook: Notebook, settings: Settings
) -> None:
    oversized = PNG + b"\x00" * (6 * 1024 * 1024)
    with pytest.raises(ImageTooLarge):
        await create_image_card(
            user=user,
            db=db,
            settings=settings,
            notebook_id=notebook.id,
            front_md="What is labeled A?",
            back_md="The mitochondria.",
            concept_id=None,
            image=upload_file(oversized),
        )


async def test_uploading_to_another_owners_notebook_is_not_found(
    db: AsyncSession, user: User, other_user: User, notebook: Notebook, settings: Settings
) -> None:
    with pytest.raises(NotFound):
        await create_image_card(
            user=other_user,
            db=db,
            settings=settings,
            notebook_id=notebook.id,
            front_md="What is labeled A?",
            back_md="The mitochondria.",
            concept_id=None,
            image=upload_file(),
        )
