"""Object storage for uploaded files.

Files are stored under generated keys, never under user-supplied names: a filename
is untrusted input, and path traversal through it is the oldest upload bug there is.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Protocol

from noema.core.config import Settings
from noema.core.errors import NoemaError

__all__ = ["LocalStorage", "Storage", "StorageError", "build_storage", "storage_key"]


class StorageError(NoemaError):
    slug = "storage-failed"
    title = "Storage failure"
    status_code = 500


def storage_key(owner_id: uuid.UUID, source_id: uuid.UUID, kind: str) -> str:
    """A key derived entirely from ids we generated."""
    return f"{owner_id}/{source_id}.{kind}"


class Storage(Protocol):
    async def put(self, key: str, data: bytes) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...


class LocalStorage:
    """Filesystem driver — the default, and enough for a single machine."""

    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        # Defence in depth: keys are generated, but a resolved path escaping the root
        # must never be written to regardless.
        if not path.is_relative_to(self.root.resolve()):
            raise StorageError("Refusing to write outside the storage root.")
        return path

    async def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise StorageError("The stored file is missing.")
        return path.read_bytes()

    async def delete(self, key: str) -> None:
        path = self._path(key)
        path.unlink(missing_ok=True)


def build_storage(settings: Settings) -> Storage:
    if settings.storage_driver == "local":
        return LocalStorage(settings.storage_local_path)
    raise StorageError(
        f"Storage driver {settings.storage_driver!r} is configured but not implemented."
    )
