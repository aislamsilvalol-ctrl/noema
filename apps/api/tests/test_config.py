"""The one setting a deployment's own platform can stamp for it, and the checks
that refuse to start a production deployment with unsafe configuration."""

from __future__ import annotations

import base64
from typing import Any

import pytest

from noema.core.config import Settings

REAL_KEY = base64.b64encode(b"0" * 32).decode()


def production_settings(**overrides: Any) -> Settings:
    """A production config that passes every existing check, so each test only
    has to override the one thing it means to break."""
    # Any: pydantic-settings' own __init__ signature is a large union of
    # CLI-source-specific literals — a **dict of mixed field types has no
    # narrower type that satisfies it.
    fields: dict[str, Any] = {
        "noema_env": "production",
        "noema_master_key": REAL_KEY,
        "noema_session_secret": REAL_KEY,
        "noema_secure_cookies": True,
        "noema_cors_origins": "https://app.example.com",
        "database_url": "postgresql+asyncpg://noema:pw@db.internal:5432/noema",
        "redis_url": "redis://cache.internal:6379/0",
        "noema_web_origin": "https://app.example.com",
        "noema_default_provider": "anthropic",
        "anthropic_api_key": "sk-ant-test",
        "noema_embedding_provider": "openai",
        "openai_api_key": "sk-test",
    }
    fields.update(overrides)
    return Settings(**fields)


def test_an_explicit_git_sha_is_used_as_is(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOEMA_GIT_SHA", "abc123")
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)

    assert Settings().noema_git_sha == "abc123"


def test_railways_own_variable_is_the_fallback_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NOEMA_GIT_SHA", raising=False)
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "def456")

    assert Settings().noema_git_sha == "def456"


def test_railways_own_variable_is_the_fallback_when_set_but_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`${{RAILWAY_GIT_COMMIT_SHA}}` as a Railway *variable* reference resolves to
    an empty string — it is a value Railway injects into the process directly, not
    one held in the variables table the reference system reads from. A deployment
    configured that way must still recover the real value.
    """
    monkeypatch.setenv("NOEMA_GIT_SHA", "")
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "def456")

    assert Settings().noema_git_sha == "def456"


def test_unknown_when_neither_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOEMA_GIT_SHA", raising=False)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)

    assert Settings().noema_git_sha == "unknown"


# ── validate_for_production ─────────────────────────────────────────────────────


def test_non_production_env_never_raises() -> None:
    """A wildcard origin and placeholder secrets are exactly what local dev uses —
    these checks must only ever apply to a real production deployment."""
    settings = Settings(
        noema_env="development",
        noema_master_key="",
        noema_session_secret="",
        noema_secure_cookies=False,
        noema_cors_origins="*",
    )

    settings.validate_for_production()


def test_a_fully_valid_production_config_does_not_raise() -> None:
    production_settings().validate_for_production()


def test_a_placeholder_master_key_is_refused() -> None:
    with pytest.raises(RuntimeError, match="NOEMA_MASTER_KEY"):
        production_settings(noema_master_key="CHANGE_ME").validate_for_production()


def test_an_empty_session_secret_is_refused() -> None:
    with pytest.raises(RuntimeError, match="NOEMA_SESSION_SECRET"):
        production_settings(noema_session_secret="").validate_for_production()


def test_insecure_cookies_are_refused_in_production() -> None:
    with pytest.raises(RuntimeError, match="NOEMA_SECURE_COOKIES"):
        production_settings(noema_secure_cookies=False).validate_for_production()


def test_a_wildcard_cors_origin_is_refused() -> None:
    """CORSMiddleware is always built with allow_credentials=True — Starlette does
    not fail closed on "*" with credentials, it reflects the request's actual
    Origin back instead, so this must never reach a running deployment."""
    with pytest.raises(RuntimeError, match="NOEMA_CORS_ORIGINS"):
        production_settings(noema_cors_origins="*").validate_for_production()


def test_a_wildcard_among_other_origins_is_still_refused() -> None:
    with pytest.raises(RuntimeError, match="NOEMA_CORS_ORIGINS"):
        production_settings(
            noema_cors_origins="https://app.example.com,*"
        ).validate_for_production()


def test_multiple_real_origins_are_fine() -> None:
    production_settings(
        noema_cors_origins="https://app.example.com,https://staging.example.com"
    ).validate_for_production()


def test_every_problem_is_reported_at_once() -> None:
    """One RuntimeError, not a fix-one-see-the-next loop."""
    with pytest.raises(RuntimeError) as exc:
        production_settings(
            noema_master_key="CHANGE_ME", noema_cors_origins="*"
        ).validate_for_production()

    assert "NOEMA_MASTER_KEY" in str(exc.value)
    assert "NOEMA_CORS_ORIGINS" in str(exc.value)


# ── required dependencies in production ────────────────────────────────────────


def test_an_unset_database_url_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default points at localhost: right for a laptop, an outage on a server."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = production_settings()
    settings.model_fields_set.discard("database_url")
    with pytest.raises(RuntimeError, match="DATABASE_URL must be set"):
        settings.validate_for_production()


def test_a_non_postgres_database_url_is_refused() -> None:
    with pytest.raises(RuntimeError, match="DATABASE_URL must be a postgresql"):
        production_settings(database_url="sqlite:///x.db").validate_for_production()


def test_a_bad_redis_url_is_refused() -> None:
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        production_settings(redis_url="localhost:6379").validate_for_production()


def test_a_missing_web_origin_is_refused() -> None:
    with pytest.raises(RuntimeError, match="NOEMA_WEB_ORIGIN must be set"):
        production_settings(noema_web_origin="").validate_for_production()


def test_a_plain_http_web_origin_is_refused() -> None:
    with pytest.raises(RuntimeError, match="NOEMA_WEB_ORIGIN must be an https"):
        production_settings(
            noema_web_origin="http://app.example.com"
        ).validate_for_production()


def test_the_default_provider_needs_its_key() -> None:
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY is not set"):
        production_settings(anthropic_api_key="").validate_for_production()


def test_the_embedding_provider_needs_its_key() -> None:
    with pytest.raises(RuntimeError, match="NOEMA_EMBEDDING_PROVIDER=openai"):
        production_settings(openai_api_key="").validate_for_production()


def test_the_mock_provider_is_refused_in_production() -> None:
    with pytest.raises(RuntimeError, match="NOEMA_DEFAULT_PROVIDER=mock"):
        production_settings(noema_default_provider="mock").validate_for_production()


def test_ollama_needs_no_key() -> None:
    production_settings(
        noema_default_provider="ollama", noema_embedding_provider="ollama"
    ).validate_for_production()


def test_problems_never_echo_a_secret_value() -> None:
    with pytest.raises(RuntimeError) as exc:
        production_settings(
            database_url="mysql://root:hunter2@db/noema",
            redis_url="tcp://:hunter3@cache",
        ).validate_for_production()
    assert "hunter2" not in str(exc.value)
    assert "hunter3" not in str(exc.value)


def test_non_production_accepts_the_mock_and_no_keys() -> None:
    Settings(
        noema_env="test",
        noema_default_provider="mock",
        noema_embedding_provider="mock",
        noema_web_origin="",
    ).validate_for_production()
