"""Deployment configuration.

One settings object, validated at import. A misconfigured deployment should fail on
startup with a readable message, never halfway through a user's first upload.
"""

from __future__ import annotations

import base64
import os
from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Mode(StrEnum):
    CLOUD = "cloud"
    LOCAL = "local"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="", env_file=".env", extra="ignore", case_sensitive=False
    )

    # ── Mode ───────────────────────────────────────────────────────────────────
    noema_mode: Mode = Mode.CLOUD
    noema_env: Literal["development", "test", "production"] = "development"
    noema_log_level: str = "info"

    # ── Data ───────────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://noema:noema@localhost:5432/noema"
    redis_url: str = "redis://localhost:6379/0"
    storage_driver: Literal["local", "s3"] = "local"
    storage_local_path: str = "/var/lib/noema/uploads"
    #: S3-compatible object storage. Any implementation works — AWS, Cloudflare
    #: R2, Backblaze, MinIO — because the only reason to need this is that the API
    #: and the worker cannot share a disk.
    s3_bucket: str = ""
    s3_region: str = "auto"
    #: Set for anything that is not AWS itself.
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""

    # ── Security ───────────────────────────────────────────────────────────────
    noema_master_key: str = ""
    noema_session_secret: str = ""
    noema_secure_cookies: bool = False
    noema_allow_signups: bool = True
    noema_cors_origins: str = "http://localhost:3000"

    access_token_ttl_seconds: int = 60 * 15
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 30

    # ── AI ─────────────────────────────────────────────────────────────────────
    noema_default_provider: str = "ollama"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    openrouter_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    noema_model_tutor: str = ""
    noema_model_extract: str = ""
    noema_model_grade: str = ""
    noema_model_summarize: str = ""

    noema_embedding_provider: str = "ollama"
    noema_embedding_model: str = "nomic-embed-text"
    noema_embedding_dim: int = 768
    #: Days an embedding stays cached. 0 disables the cache entirely — see
    #: `noema.providers.cache` for the one privacy trade-off it carries.
    noema_embedding_cache_ttl_days: int = 30

    #: The commit this deployment was built from, reported by `/api/v1/meta`.
    #: "unknown" is the honest answer for a build that was not stamped, and the
    #: checker treats it as a failure rather than a pass — a deployment that
    #: cannot say what it is running is exactly the thing being guarded against.
    #:
    #: Every deploy between 12 and 14 August failed while the previous container
    #: stayed healthy and kept serving. The platform said "Online", the build log
    #: ended in "Healthcheck succeeded" (belonging to the last good build), and
    #: production ran two-day-old code unnoticed. Nothing was wrong with the
    #: running service; what was missing was any way to ask it which code it was.
    #:
    #: `RAILWAY_GIT_COMMIT_SHA` falls back for a deploy that never got NOEMA_GIT_SHA
    #: set explicitly: Railway injects it into the container's own process
    #: environment for a GitHub-triggered build, which is not the same thing as it
    #: being a referenceable Railway *variable* — `${{RAILWAY_GIT_COMMIT_SHA}}`
    #: resolves to empty, because the reference system reads from the variables
    #: table this was never added to.
    noema_git_sha: str = "unknown"

    # ── Limits ─────────────────────────────────────────────────────────────────
    noema_max_upload_mb: int = 100
    noema_user_storage_quota_mb: int = 2048
    noema_rate_limit_per_minute: int = 120
    # Far tighter, because these are the endpoints worth guessing at. Generous for a
    # human signing in, useless as a credential-stuffing budget.
    noema_auth_rate_limit_per_minute: int = 10
    #: How many proxies sit in front of this deployment. 0 means none: the socket
    #: address is the caller. Anything higher makes the limiter read
    #: `X-Forwarded-For`, skipping that many entries from the right — everything
    #: left of them is caller-supplied and must not be believed.
    noema_trusted_proxy_hops: int = 0
    noema_ai_daily_token_budget: int = 1_000_000
    #: Share of the daily token budget held back for interactive use. Batch
    #: generation stops at the reserve line so the tutor still answers when a
    #: runaway generation loop has eaten the day.
    noema_ai_interactive_reserve: float = Field(default=0.15, ge=0.0, lt=1.0)

    # ── Learning ───────────────────────────────────────────────────────────────
    noema_fsrs_target_retention: float = Field(default=0.90, gt=0.5, lt=1.0)
    noema_fsrs_optimize_min_reviews: int = 400
    noema_mastery_model_version: int = 1

    @field_validator("noema_git_sha", mode="after")
    @classmethod
    def _fallback_to_railways_own_git_sha(cls, value: str) -> str:
        if value and value != "unknown":
            return value
        return os.environ.get("RAILWAY_GIT_COMMIT_SHA") or "unknown"

    @field_validator("noema_master_key", "noema_session_secret")
    @classmethod
    def _validate_secret(cls, value: str) -> str:
        if not value or value.startswith("CHANGE_ME"):
            # Empty is tolerated in development so a clone runs before configuration;
            # production is checked separately in `validate_for_production`.
            return value
        try:
            decoded = base64.b64decode(value, validate=True)
        except Exception as exc:
            raise ValueError("must be base64-encoded") from exc
        if len(decoded) != 32:
            raise ValueError(f"must decode to 32 bytes, got {len(decoded)}")
        return value

    @property
    def session_secret_bytes(self) -> bytes:
        """The session secret as raw bytes, for keyed hashing.

        Empty in development, where the secret itself is empty — a keyed hash with
        an empty key is still stable, and nothing in development depends on it
        being unguessable.
        """
        return (
            base64.b64decode(self.noema_session_secret)
            if self.noema_session_secret
            else b""
        )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.noema_cors_origins.split(",") if o.strip()]

    @property
    def is_local_mode(self) -> bool:
        return self.noema_mode is Mode.LOCAL

    def validate_for_production(self) -> None:
        """Refuse to start a production deployment with placeholder secrets."""
        if self.noema_env != "production":
            return
        problems = []
        for name in ("noema_master_key", "noema_session_secret"):
            value = getattr(self, name)
            if not value or value.startswith("CHANGE_ME"):
                problems.append(f"{name.upper()} must be set to a real 32-byte key")
        if not self.noema_secure_cookies:
            problems.append("NOEMA_SECURE_COOKIES must be true in production")
        if "*" in self.cors_origins:
            # CORSMiddleware is always built with allow_credentials=True (see
            # create_app()); Starlette does not fail closed on this combination —
            # it reflects the request's actual Origin back instead of the literal
            # "*", which defeats the cookie/CSRF auth model for every origin.
            problems.append(
                "NOEMA_CORS_ORIGINS must not be '*' — a wildcard origin with "
                "credentialed CORS defeats the cookie/CSRF auth model"
            )
        if problems:
            raise RuntimeError(
                "Invalid production configuration:\n  - " + "\n  - ".join(problems)
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
