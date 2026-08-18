"""The one setting a deployment's own platform can stamp for it."""

from __future__ import annotations

import pytest

from noema.core.config import Settings


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
