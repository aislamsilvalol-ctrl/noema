"""Dependency checks for readiness and the admin ops view.

Liveness (`/health`) answers "is the process up" and touches nothing, so a
platform that restarts on a failed liveness probe never restarts a healthy
process because Postgres blinked. Readiness answers "can this instance serve
traffic right now" and is allowed to say no: each dependency is checked with
a short timeout, so a hung database makes the probe fail fast rather than hang.

Results name the dependency and the *class* of failure, never its message: a
driver error can carry a hostname, a user or a DSN.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

#: Per dependency. A probe that waits longer than this has already answered.
CHECK_TIMEOUT_SECONDS = 2.0

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


@dataclass(frozen=True, slots=True)
class Check:
    ok: bool
    detail: str = "ok"

    def __str__(self) -> str:
        return self.detail


def _failure(exc: BaseException) -> Check:
    if isinstance(exc, TimeoutError):
        return Check(False, "error: timeout")
    return Check(False, f"error: {type(exc).__name__}")


@lru_cache(maxsize=1)
def code_migration_heads() -> frozenset[str]:
    """The Alembic head(s) this build ships with, read once from the scripts."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(_ALEMBIC_INI))
    config.set_main_option("script_location", str(_ALEMBIC_INI.parent / "alembic"))
    config.set_main_option("path_separator", "os")
    return frozenset(ScriptDirectory.from_config(config).get_heads())


async def check_database(engine: AsyncEngine) -> tuple[Check, str | None]:
    """`SELECT 1`, plus the schema revision the database is at (None if unknown)."""

    async def probe() -> str | None:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            try:
                version = await conn.scalar(
                    text("SELECT version_num FROM alembic_version")
                )
            except Exception:
                return None
            return str(version) if version else None

    try:
        revision = await asyncio.wait_for(probe(), timeout=CHECK_TIMEOUT_SECONDS)
    except Exception as exc:
        return _failure(exc), None
    return Check(True), revision


def check_migrations(db_revision: str | None) -> Check:
    try:
        heads = code_migration_heads()
    except Exception as exc:
        return _failure(exc)
    if db_revision is None:
        return Check(False, "error: no alembic_version")
    if db_revision in heads:
        return Check(True)
    # Revision ids are not secrets, and naming both is what makes this
    # actionable: "behind" means the pre-deploy migration did not run.
    code = ",".join(sorted(heads))
    return Check(False, f"error: database at {db_revision}, code at {code}")


async def check_redis(redis: Any) -> Check:
    if redis is None:
        return Check(False, "error: not configured")
    try:
        await asyncio.wait_for(redis.ping(), timeout=CHECK_TIMEOUT_SECONDS)
    except Exception as exc:
        return _failure(exc)
    return Check(True)


async def readiness(engine: AsyncEngine, redis: Any) -> tuple[bool, dict[str, str]]:
    """Every dependency, checked concurrently. Returns (ready, per-check detail)."""
    (database, revision), redis_check = await asyncio.gather(
        check_database(engine), check_redis(redis)
    )
    migrations = check_migrations(revision) if database.ok else Check(False, "unknown")
    checks = {"database": database, "redis": redis_check, "migrations": migrations}
    return all(c.ok for c in checks.values()), {k: str(v) for k, v in checks.items()}
