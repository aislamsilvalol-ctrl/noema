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
