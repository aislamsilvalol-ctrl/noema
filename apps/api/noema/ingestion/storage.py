"""Object storage for uploaded files.

Files are stored under generated keys, never under user-supplied names: a filename
is untrusted input, and path traversal through it is the oldest upload bug there is.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any, Protocol

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


class S3Storage:
    """Any S3-compatible object store.

    Exists for one reason: the API and the worker cannot share a disk unless they
    share a machine. With the local driver the worker has to run inside the API's
    container to see an upload, which means it cannot be scaled separately — the
    whole point of having a worker.

    boto3 rather than a hand-rolled signer: SigV4 is a specification you get
    subtly wrong and find out about in production. It is synchronous, so calls go
    to a thread — this path moves whole documents, not request-shaped payloads,
    and blocking the event loop on a 40MB PDF would stall every other request on
    the process.
    """

    def __init__(self, client: Any, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    async def put(self, key: str, data: bytes) -> None:
        try:
            await asyncio.to_thread(
                self._client.put_object, Bucket=self._bucket, Key=key, Body=data
            )
        except Exception as exc:  # every SDK error means the same thing here
            raise StorageError(f"The file could not be stored: {exc}") from exc

    async def get(self, key: str) -> bytes:
        try:
            response = await asyncio.to_thread(
                self._client.get_object, Bucket=self._bucket, Key=key
            )
            body: bytes = await asyncio.to_thread(response["Body"].read)
            return body
        except Exception as exc:
            # Deliberately the same message the local driver uses for a missing
            # file: callers already handle "the stored file is missing" and should
            # not have to learn a second vocabulary per driver.
            raise StorageError("The stored file is missing.") from exc

    async def delete(self, key: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.delete_object, Bucket=self._bucket, Key=key
            )
        except Exception as exc:
            raise StorageError(f"The file could not be deleted: {exc}") from exc


def build_storage(settings: Settings) -> Storage:
    if settings.storage_driver == "local":
        return LocalStorage(settings.storage_local_path)

    if settings.storage_driver == "s3":
        if not settings.s3_bucket:
            raise StorageError(
                "STORAGE_DRIVER is s3 but S3_BUCKET is empty. Refusing to start "
                "rather than accept uploads with nowhere to put them."
            )
        import boto3

        client = boto3.client(
            "s3",
            region_name=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url or None,
            aws_access_key_id=settings.s3_access_key_id or None,
            aws_secret_access_key=settings.s3_secret_access_key or None,
        )
        return S3Storage(client, settings.s3_bucket)

    raise StorageError(
        f"Storage driver {settings.storage_driver!r} is configured but not implemented."
    )
