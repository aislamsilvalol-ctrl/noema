"""Local object storage.

Keys are generated from ids we control, but the driver still refuses to write
outside its root: filenames are untrusted input and path traversal through them is
the oldest upload bug there is.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from noema.ingestion.storage import LocalStorage, StorageError, storage_key


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(str(tmp_path))


async def test_round_trip(storage: LocalStorage) -> None:
    await storage.put("a/b.md", b"# Notes")
    assert await storage.get("a/b.md") == b"# Notes"


async def test_delete_is_idempotent(storage: LocalStorage) -> None:
    await storage.put("a/b.md", b"x")
    await storage.delete("a/b.md")
    await storage.delete("a/b.md")

    with pytest.raises(StorageError, match="missing"):
        await storage.get("a/b.md")


async def test_traversal_outside_the_root_is_refused(storage: LocalStorage) -> None:
    with pytest.raises(StorageError, match="outside"):
        await storage.put("../escaped.md", b"nope")
    with pytest.raises(StorageError, match="outside"):
        await storage.get("../../etc/passwd")


def test_keys_are_built_from_ids_never_from_filenames() -> None:
    owner, source = uuid.uuid4(), uuid.uuid4()
    key = storage_key(owner, source, "pdf")

    assert key == f"{owner}/{source}.pdf"
    assert ".." not in key


# ── The S3 driver ────────────────────────────────────────────────────────────
#
# Against a stub rather than a real bucket: what is worth pinning is the contract
# the rest of the system relies on — round trips, and a missing object failing the
# same way it does on a local disk — not that boto3 can talk to AWS.


class StubS3:
    """Boto3's own keyword names, PascalCase and all — a stub that renamed them
    would not be standing in for the thing it is standing in for."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(
        self,
        *,
        Bucket: str,  # noqa: N803
        Key: str,  # noqa: N803
        Body: bytes,  # noqa: N803
    ) -> dict[str, object]:
        self.objects[(Bucket, Key)] = Body
        return {}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:  # noqa: N803
        data = self.objects[(Bucket, Key)]

        class Body:
            @staticmethod
            def read() -> bytes:
                return data

        return {"Body": Body}

    def delete_object(self, *, Bucket: str, Key: str) -> dict[str, object]:  # noqa: N803
        self.objects.pop((Bucket, Key), None)
        return {}


@pytest.mark.asyncio
async def test_s3_round_trips_bytes_unchanged() -> None:
    from noema.ingestion.storage import S3Storage

    stub = StubS3()
    storage = S3Storage(stub, "noema")
    payload = b"%PDF-1.7\x00\x01binary\xff"

    await storage.put("a/b/c.pdf", payload)

    assert await storage.get("a/b/c.pdf") == payload


@pytest.mark.asyncio
async def test_a_missing_object_fails_the_same_way_a_missing_file_does() -> None:
    """Callers already handle "the stored file is missing".

    Two vocabularies for the same condition would mean every caller learning
    which driver it is talking to.
    """
    from noema.ingestion.storage import S3Storage, StorageError

    storage = S3Storage(StubS3(), "noema")

    with pytest.raises(StorageError, match="missing"):
        await storage.get("never/written")


@pytest.mark.asyncio
async def test_deleting_something_absent_is_not_an_error() -> None:
    """The account purge deletes many keys; one already gone must not stop it."""
    from noema.ingestion.storage import S3Storage

    storage = S3Storage(StubS3(), "noema")
    await storage.delete("never/written")


def test_s3_without_a_bucket_refuses_to_start() -> None:
    """Better than accepting uploads with nowhere to put them."""
    from noema.core.config import Settings
    from noema.ingestion.storage import StorageError, build_storage

    settings = Settings(storage_driver="s3", s3_bucket="")

    with pytest.raises(StorageError, match="S3_BUCKET"):
        build_storage(settings)
