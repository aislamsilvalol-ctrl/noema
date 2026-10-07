"""What an operator needs at a glance: are the dependencies up, are the AI
providers answering, is the queue moving, when did the last backup land, and
how much failed in the last day.

Everything here is a cheap read with a short timeout, and nothing carries a
secret or a provider's own words: dependency failures are error classes,
providers are circuit states and error classes (`noema.providers.circuit`).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from noema.core.config import Settings
from noema.core.health import CHECK_TIMEOUT_SECONDS, readiness
from noema.core.logging import get_logger
from noema.db.models import AIUsage, FeedbackReport, Source, SourceStatus
from noema.providers.circuit import all_breakers

log = get_logger(__name__)

#: Where the db-backup cron (infra/db-backup) writes its dumps.
BACKUP_PREFIX = "postgres/"
#: Dramatiq's Redis broker keeps each queue's messages in this hash until acked.
QUEUES = ("default",)


@dataclass(slots=True)
class OpsReport:
    ready: bool
    checks: dict[str, str]
    providers: list[dict[str, Any]]
    queues: dict[str, int | None]
    dead_letters: dict[str, int | None]
    last_backup_at: datetime | None
    backup_status: str
    window_hours: int
    ai_calls: int
    ai_failures: int
    ingestion_failures: int
    feedback_reports: int
    notes: list[str] = field(default_factory=list)


def provider_status(settings: Settings) -> list[dict[str, Any]]:
    """Every provider this deployment is configured to use, plus any other
    this process has called, with its circuit state."""
    seen = {b.name: b.snapshot() for b in all_breakers()}
    configured = {
        settings.noema_default_provider: "default",
        settings.noema_embedding_provider: "embeddings",
    }
    for name in ("anthropic", "openai"):
        if getattr(settings, f"{name}_api_key", ""):
            configured.setdefault(name, "fallback")
    rows = []
    for name in sorted(set(configured) | set(seen)):
        snapshot = seen.get(name) or {
            "provider": name,
            "state": "closed",
            "recent_failures": 0,
            "last_error": None,
            "last_failure_at": None,
            "opened_total": 0,
            "retry_in_seconds": None,
        }
        last = snapshot.get("last_failure_at")
        rows.append(
            {
                **snapshot,
                "role": configured.get(name, "byok"),
                "last_failure_at": datetime.fromtimestamp(last, UTC) if last else None,
            }
        )
    return rows


async def queue_depths(redis: Any) -> tuple[dict[str, int | None], dict[str, int | None]]:
    """Messages waiting or in flight per Dramatiq queue, and dead letters."""
    depths: dict[str, int | None] = {}
    dead: dict[str, int | None] = {}
    for queue in QUEUES:
        try:
            if redis is None:
                raise ConnectionError("no redis")
            depth, dlq = await asyncio.wait_for(
                asyncio.gather(
                    redis.hlen(f"dramatiq:{queue}.msgs"),
                    redis.hlen(f"dramatiq:{queue}.DQ.msgs"),
                ),
                timeout=CHECK_TIMEOUT_SECONDS,
            )
            depths[queue], dead[queue] = int(depth), int(dlq)
        except Exception as exc:
            log.info("ops.queue_unavailable", error=type(exc).__name__)
            depths[queue] = dead[queue] = None
    return depths, dead


async def last_backup(settings: Settings) -> tuple[datetime | None, str]:
    """The newest dump in the backup bucket, when this service can see it.

    The API normally has no credentials for the backup bucket; then the answer
    is "unknown", which is true, rather than a guess.
    """
    if not (
        settings.noema_backup_bucket
        and settings.noema_backup_access_key_id
        and settings.noema_backup_secret_access_key
    ):
        return None, "unknown"

    def newest() -> datetime | None:
        import boto3

        client = boto3.client(
            "s3",
            region_name=settings.noema_backup_region or "auto",
            endpoint_url=settings.noema_backup_endpoint_url or None,
            aws_access_key_id=settings.noema_backup_access_key_id,
            aws_secret_access_key=settings.noema_backup_secret_access_key,
        )
        latest: datetime | None = None
        for page in client.get_paginator("list_objects_v2").paginate(
            Bucket=settings.noema_backup_bucket, Prefix=BACKUP_PREFIX
        ):
            for obj in page.get("Contents", []):
                modified = obj["LastModified"]
                if latest is None or modified > latest:
                    latest = modified
        return latest

    try:
        latest = await asyncio.wait_for(asyncio.to_thread(newest), timeout=10)
    except Exception as exc:
        return None, f"error: {type(exc).__name__}"
    if latest is None:
        return None, "error: no backups found"
    stale = datetime.now(UTC) - latest > timedelta(hours=36)
    return latest, "stale" if stale else "ok"


async def build_report(
    db: AsyncSession,
    *,
    engine: AsyncEngine,
    redis: Any,
    settings: Settings,
    window_hours: int = 24,
) -> OpsReport:
    since = datetime.now(UTC) - timedelta(hours=window_hours)
    (ready, checks), (depths, dead), (backup_at, backup_status) = await asyncio.gather(
        readiness(engine, redis), queue_depths(redis), last_backup(settings)
    )

    ai_calls, ai_failures = (
        await db.execute(
            select(
                func.count(),
                func.count().filter(AIUsage.succeeded.is_(False)),
            ).where(AIUsage.created_at >= since)
        )
    ).one()
    ingestion_failures = await db.scalar(
        select(func.count())
        .select_from(Source)
        .where(Source.status == SourceStatus.FAILED, Source.updated_at >= since)
    )
    feedback = await db.scalar(
        select(func.count())
        .select_from(FeedbackReport)
        .where(FeedbackReport.created_at >= since)
    )
    return OpsReport(
        ready=ready,
        checks=checks,
        providers=provider_status(settings),
        queues=depths,
        dead_letters=dead,
        last_backup_at=backup_at,
        backup_status=backup_status,
        window_hours=window_hours,
        ai_calls=int(ai_calls or 0),
        ai_failures=int(ai_failures or 0),
        ingestion_failures=int(ingestion_failures or 0),
        feedback_reports=int(feedback or 0),
        notes=[
            "Circuit state is per API process and resets on deploy.",
            "HTTP 5xx counts are not stored; see the platform's metrics.",
        ],
    )
