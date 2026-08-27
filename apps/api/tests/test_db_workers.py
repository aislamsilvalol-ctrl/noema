"""The background actors, against a real database.

`ingest()` and `purge_accounts()` are thin dramatiq wrappers around
`_ingest()`/`_purge()`, which each open a session on their own throwaway engine
via `_session()` rather than sharing the caller's or the process-wide pool —
deliberately, since every actor invocation is its own `asyncio.run()`, in its
own event loop. That means these tests can't use the `db` fixture's rolled-back
transaction like the rest of the suite either: setup and verification go
through that same `_session()` helper, the same way the real worker process
does, and clean up after themselves by relying on the same deletion/failure
logic under test.

`ingest()` and `purge_accounts()` themselves call `asyncio.run(...)`, which
cannot run inside pytest-asyncio's event loop — so the two tests that call the
actors directly are plain, synchronous `def` tests with no async fixtures.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import text

from noema.db.base import utcnow
from noema.db.models import (
    Notebook,
    Source,
    SourceKind,
    SourceStatus,
    Subject,
    User,
    Workspace,
)
from noema.db.repository import OwnedRepository
from noema.ingestion.storage import LocalStorage
from noema.services.account import GRACE_DAYS, request_deletion
from noema.services.auth import AuthService
from noema.workers import _ingest, _session, ingest, purge_accounts

REQUIRE_DB = os.environ.get("NOEMA_REQUIRE_DB") == "1"


def _skip_if_unreachable(exc: Exception) -> None:
    if REQUIRE_DB:
        raise exc
    pytest.skip(f"no database available: {type(exc).__name__}")


async def _make_expired_user(email: str) -> uuid.UUID:
    from noema.core.config import get_settings

    async with _session() as session:
        user = await AuthService(session, get_settings()).register(
            email, "correct-horse-battery", "Purge Me"
        )
        await request_deletion(session, user)
        user.deleted_at = utcnow() - timedelta(days=GRACE_DAYS + 1)
        await session.commit()
        return user.id


async def _get_user(user_id: uuid.UUID) -> User | None:
    async with _session() as session:
        return await session.get(User, user_id)


def test_purge_accounts_actor_deletes_an_expired_user() -> None:
    email = f"purge-{uuid.uuid4().hex[:8]}@example.com"
    try:
        user_id = asyncio.run(_make_expired_user(email))
    except Exception as exc:
        _skip_if_unreachable(exc)
        return

    purge_accounts()

    assert asyncio.run(_get_user(user_id)) is None


async def _make_source(
    email: str, *, storage_key: str | None
) -> tuple[uuid.UUID, uuid.UUID]:
    """A committed user + notebook + source, ready for a real ingest run."""
    async with _session() as session:
        from noema.core.config import get_settings

        user = await AuthService(session, get_settings()).register(
            email, "correct-horse-battery", "Ingest Me"
        )
        workspace = await OwnedRepository(session, Workspace, user.id).create(
            title="Bio", slug=f"bio-{uuid.uuid4().hex[:8]}"
        )
        subject = await OwnedRepository(session, Subject, user.id).create(
            workspace_id=workspace.id, title="Cells", slug=f"cells-{uuid.uuid4().hex[:8]}"
        )
        notebook = await OwnedRepository(session, Notebook, user.id).create(
            subject_id=subject.id,
            title="Organelles",
            slug=f"org-{uuid.uuid4().hex[:8]}",
            retrieval_settings={},
        )
        source = await OwnedRepository(session, Source, user.id).create(
            notebook_id=notebook.id,
            kind=SourceKind.MD,
            original_filename="notes.md",
            byte_size=0,
            status=SourceStatus.PENDING,
            storage_key=storage_key,
        )
        await session.commit()
        return user.id, source.id


async def _get_source(source_id: uuid.UUID) -> Source | None:
    async with _session() as session:
        return await session.get(Source, source_id)


def test_ingest_actor_processes_a_source_end_to_end(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The full wiring: router → provider → gateway → pipeline → commit."""
    import noema.workers as workers_module

    monkeypatch.setattr(workers_module.settings, "noema_embedding_provider", "mock")
    monkeypatch.setattr(workers_module.settings, "storage_local_path", str(tmp_path))

    async def make() -> uuid.UUID:
        storage = LocalStorage(str(tmp_path))
        key = f"test-ingest/{uuid.uuid4().hex}.md"
        await storage.put(key, b"# Mitochondria\n\nThe powerhouse of the cell.\n")
        _, source_id = await _make_source(
            f"ingest-actor-{uuid.uuid4().hex[:8]}@example.com", storage_key=key
        )
        return source_id

    try:
        source_id = asyncio.run(make())
        # Redis-backed embedding cache is on this path too, unlike the fallback
        # test below — wrapped in the same skip-guard as the database setup.
        ingest(str(source_id))
    except Exception as exc:
        _skip_if_unreachable(exc)
        return

    source = asyncio.run(_get_source(source_id))
    assert source is not None
    assert source.status is SourceStatus.READY
    assert source.error is None


async def test_a_missing_embedding_provider_still_lets_ingestion_finish(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`_ingest` falls back to text-only search rather than failing the source."""
    import noema.api.v1.deps as deps_module
    import noema.workers as workers_module

    async def broken_build_provider(*args: object, **kwargs: object) -> object:
        raise RuntimeError("no embedding provider configured for this test")

    monkeypatch.setattr(deps_module, "build_provider", broken_build_provider)
    monkeypatch.setattr(workers_module.settings, "storage_local_path", str(tmp_path))

    storage = LocalStorage(str(tmp_path))
    key = f"test-ingest/{uuid.uuid4().hex}.md"
    try:
        await storage.put(key, b"# Ribosome\n\nSynthesizes proteins.\n")
        _, source_id = await _make_source(
            f"ingest-fallback-{uuid.uuid4().hex[:8]}@example.com", storage_key=key
        )
    except Exception as exc:
        _skip_if_unreachable(exc)
        return

    await _ingest(source_id)

    source = await _get_source(source_id)
    assert source is not None
    assert source.status is SourceStatus.READY


async def test_a_second_concurrent_ingest_of_the_same_source_is_a_no_op() -> None:
    """Two `/ingest` calls landing close together must not race on one source.

    `_ingest` takes a Postgres advisory lock keyed by the source id before
    running the pipeline. Holding that same key from a second connection here
    stands in for a second dramatiq thread having already claimed the run —
    `_ingest` must return cleanly without touching the source, not attempt the
    pipeline (which would raise, since this source has no stored file).
    """
    try:
        _, source_id = await _make_source(
            f"ingest-concurrent-{uuid.uuid4().hex[:8]}@example.com", storage_key=None
        )
    except Exception as exc:
        _skip_if_unreachable(exc)
        return

    lock_key = source_id.int & 0x7FFFFFFFFFFFFFFF
    async with _session() as holder:
        acquired = await holder.scalar(
            text("SELECT pg_try_advisory_lock(:key)").bindparams(key=lock_key)
        )
        assert acquired, "test setup: could not take the lock _ingest is meant to see"

        # Must not raise: a broken guard would fall through to ingest_source,
        # which raises ValueError on this source's missing storage_key.
        await _ingest(source_id)

    source = await _get_source(source_id)
    assert source is not None
    assert source.status is SourceStatus.PENDING
    assert source.error is None


async def test_a_pipeline_failure_still_gets_committed_before_reraising() -> None:
    """`ingest_source` records the failure but only flushes it — `_ingest` must
    commit that write itself, or a queued job's failure reason would vanish."""
    try:
        _, source_id = await _make_source(
            f"ingest-failure-{uuid.uuid4().hex[:8]}@example.com", storage_key=None
        )
    except Exception as exc:
        _skip_if_unreachable(exc)
        return

    with pytest.raises(ValueError, match="no stored file"):
        await _ingest(source_id)

    source = await _get_source(source_id)
    assert source is not None
    assert source.status is SourceStatus.FAILED
    assert source.error is not None
