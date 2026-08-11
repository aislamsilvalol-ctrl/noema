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
