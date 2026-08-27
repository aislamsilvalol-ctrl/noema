"""Background actors.

Ingestion runs here rather than in the request path: parsing a 300-page PDF takes
minutes and processes untrusted input, neither of which belongs in a web worker.

The actor is a thin shell around :func:`noema.ingestion.pipeline.ingest_source` so
the pipeline itself stays a plain async function that tests can call directly.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from noema.core.config import get_settings
from noema.core.logging import configure_logging, get_logger
from noema.ingestion.pipeline import ingest_source
from noema.ingestion.storage import build_storage

settings = get_settings()
configure_logging(
    settings.noema_log_level, json_output=settings.noema_env != "development"
)
log = get_logger(__name__)

broker = RedisBroker(url=settings.redis_url)
dramatiq.set_broker(broker)


@dramatiq.actor(
    max_retries=3,
    min_backoff=5_000,
    max_backoff=300_000,
    # Long enough for a large PDF, short enough that a wedged job is not permanent.
    time_limit=30 * 60 * 1000,
)
def ingest(source_id: str) -> None:
    """Ingest one source. Retried on failure; the stage is recorded on the row."""
    asyncio.run(_ingest(uuid.UUID(source_id)))


@dramatiq.actor(max_retries=1, time_limit=10 * 60 * 1000)
def purge_accounts() -> None:
    """Permanently delete accounts past their grace period.

    Dramatiq has no scheduler, so this is triggered rather than periodic — by cron,
    by a platform scheduler, or by hand. `docs/self-hosting.md` says which, because
    an unrun purge means "deleted" quietly means "hidden".
    """
    asyncio.run(_purge())


@asynccontextmanager
async def _session() -> AsyncIterator[AsyncSession]:
    """A session on a throwaway, per-call engine.

    Not ``noema.db.base``'s shared pool: every actor invocation is its own
    ``asyncio.run()``, in its own event loop, and a pooled asyncpg connection is
    bound to the loop that created it — reusing a process-wide pool across
    invocations hands the next job a connection tied to a loop that no longer
    exists. A dedicated engine, opened and disposed within the one loop that
    uses it, sidesteps that rather than working around it.
    """
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with maker() as session:
            yield session
    finally:
        await engine.dispose()


async def _purge() -> None:
    from noema.services.account import purge_expired_accounts

    async with _session() as session:
        purged = await purge_expired_accounts(session, storage=build_storage(settings))
        await session.commit()
        if purged:
            log.info("worker.accounts_purged", count=len(purged))


async def _ingest(source_id: uuid.UUID) -> None:
    from noema.api.v1.deps import build_provider
    from noema.providers.base import TaskClass
    from noema.providers.gateway import AIGateway
    from noema.providers.registry import Router

    router = Router(
        default_provider=settings.noema_default_provider,
        embedding_provider=settings.noema_embedding_provider,
    )
    route = router.resolve(TaskClass.EMBED)

    gateway: AIGateway | None
    try:
        # This is the path that embeds a 600-chunk textbook, so it is the one the
        # cache exists for. Re-ingesting after a chunking change should not buy the
        # same vectors twice.
        from noema.providers.cache import EmbeddingCache

        gateway = AIGateway(
            await build_provider(route.provider, settings, None),
            embeddings=EmbeddingCache(
                Redis.from_url(settings.redis_url),
                ttl_days=settings.noema_embedding_cache_ttl_days,
            ),
        )
    except Exception as exc:
        # No embedding provider means text search only, which is worth having.
        log.warning("worker.embeddings_unavailable", error=str(exc))
        gateway = None

    async with _session() as session:
        # `POST /sources/{id}/ingest` is deliberately re-triggerable while a
        # source is still `pending` -- that is the only way to recover a source
        # whose first `ingest.send()` never actually happened (a dropped
        # connection between upload and the ingest call). But it also means two
        # requests close together can both queue a message before either has
        # run, and with `--threads 4` in production both can be picked up
        # concurrently. `ingest_source` deletes and rebuilds this source's
        # chunks from scratch, so two runs racing on the same source_id can
        # each stomp the other's rows mid-pipeline. An advisory lock, held for
        # the run and released implicitly when this call's dedicated engine is
        # disposed below, makes the second arrival a clean no-op instead of a
        # race -- the first run still owns the source and will finish it.
        lock_key = source_id.int & 0x7FFFFFFFFFFFFFFF
        acquired = await session.scalar(
            text("SELECT pg_try_advisory_lock(:key)").bindparams(key=lock_key)
        )
        if not acquired:
            log.info("ingestion.already_in_flight", source_id=str(source_id))
            return

        try:
            await ingest_source(
                session,
                source_id,
                storage=build_storage(settings),
                gateway=gateway,
                settings=settings,
            )
            await session.commit()
        except Exception:
            # The pipeline already recorded the failure on the source row, and that
            # write has to survive — otherwise the user sees a job stuck mid-stage
            # with no explanation. A commit that itself fails must not mask the
            # original error.
            try:
                await session.commit()
            except Exception:
                await session.rollback()
            raise
