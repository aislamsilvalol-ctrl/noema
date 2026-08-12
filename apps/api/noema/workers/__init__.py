"""Background actors.

Ingestion runs here rather than in the request path: parsing a 300-page PDF takes
minutes and processes untrusted input, neither of which belongs in a web worker.

The actor is a thin shell around :func:`noema.ingestion.pipeline.ingest_source` so
the pipeline itself stays a plain async function that tests can call directly.
"""

from __future__ import annotations

import asyncio
import uuid

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from noema.core.config import get_settings
from noema.core.logging import configure_logging, get_logger
from noema.db.base import get_sessionmaker
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


async def _purge() -> None:
    from noema.services.account import purge_expired_accounts

    async with get_sessionmaker()() as session:
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
        gateway = AIGateway(await build_provider(route.provider, settings, None))
    except Exception as exc:
        # No embedding provider means text search only, which is worth having.
        log.warning("worker.embeddings_unavailable", error=str(exc))
        gateway = None

    async with get_sessionmaker()() as session:
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
