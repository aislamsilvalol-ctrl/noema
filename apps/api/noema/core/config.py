"""Deployment configuration.

One settings object, validated at import. A misconfigured deployment should fail on
startup with a readable message, never halfway through a user's first upload.
"""

from __future__ import annotations

import base64
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

    # ── Limits ─────────────────────────────────────────────────────────────────
    noema_max_upload_mb: int = 100
    noema_user_storage_quota_mb: int = 2048
    noema_rate_limit_per_minute: int = 120
    noema_ai_daily_token_budget: int = 1_000_000

    # ── Learning ───────────────────────────────────────────────────────────────
    noema_fsrs_target_retention: float = Field(default=0.90, gt=0.5, lt=1.0)
    noema_fsrs_optimize_min_reviews: int = 400
    noema_mastery_model_version: int = 1

    @field_validator("noema_master_key", "noema_session_secret")
    @classmethod
    def _validate_secret(cls, value: str) -> str:
        if not value or value.startswith("CHANGE_ME"):
            # Empty is tolerated in development so a clone runs before configuration;
            # production is checked separately in `validate_for_production`.
            return value
        try:
            decoded = base64.b64decode(value, validate=True)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("must be base64-encoded") from exc
        if len(decoded) != 32:
            raise ValueError(f"must decode to 32 bytes, got {len(decoded)}")
        return value

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
        if problems:
            raise RuntimeError("Invalid production configuration:\n  - " + "\n  - ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()
