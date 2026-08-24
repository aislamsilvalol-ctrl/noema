"""Tests for the `/auth` route layer itself — cookie semantics and the request/
response glue around `AuthService`, which `test_db_auth.py` already covers on its
own terms. What is unique here and worth pinning down: the session cookie must be
httpOnly while the CSRF cookie must not be (that's the whole point of the split —
the SPA reads one and never sees the other), both must inherit `secure` from
settings rather than a hardcoded value, and the "no cookie" paths (`refresh` with
nothing to refresh, `logout` with nothing to log out of) must behave the way a
never-logged-in browser needs them to.
"""

from __future__ import annotations

from http.cookies import Morsel, SimpleCookie

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import Response

from noema.api.v1 import deps
from noema.api.v1.auth import login, logout, refresh, register
from noema.api.v1.schemas import LoginRequest, RegisterRequest
from noema.core.config import Settings
from noema.core.errors import Unauthorized
from noema.db.models import User
from noema.services.auth import AuthService


def request_with_cookie(token: str | None) -> Request:
    headers = [(b"cookie", f"{deps.SESSION_COOKIE}={token}".encode())] if token else []
    return Request(
        {
            "type": "http",
            "headers": headers,
            "client": ("10.0.0.1", 1234),
            "method": "POST",
            "path": "/",
        }
    )


def cookies_from(response: Response) -> dict[str, Morsel[str]]:
    """One parsed cookie morsel per `Set-Cookie` header, keyed by cookie name."""
    out: dict[str, Morsel[str]] = {}
    for raw in response.headers.getlist("set-cookie"):
        jar: SimpleCookie = SimpleCookie()
        jar.load(raw)
        out.update(jar)
    return out


async def test_register_sets_httponly_session_and_readable_csrf_cookie(
    db: AsyncSession, settings: Settings
) -> None:
    response = Response()
    await register(
        RegisterRequest(
            email="new@example.com", password="correct-horse-battery", display_name="New"
        ),
        request_with_cookie(None),
        response,
        db,
        settings,
    )

    jar = cookies_from(response)
    session_cookie = jar[deps.SESSION_COOKIE]
    csrf_cookie = jar[deps.CSRF_COOKIE]

    assert session_cookie["httponly"], "the refresh token must never be JS-readable"
    assert not csrf_cookie["httponly"], (
        "the SPA echoes this one back in a header — it has to be readable"
    )
    for cookie in (session_cookie, csrf_cookie):
        assert cookie["path"] == "/"
        assert cookie["samesite"] == "lax"
        assert int(cookie["max-age"]) == settings.refresh_token_ttl_seconds


async def test_secure_flag_follows_settings_not_a_hardcoded_default(
    db: AsyncSession, settings: Settings
) -> None:
    settings.noema_secure_cookies = True
    response = Response()
    await register(
        RegisterRequest(
            email="secure@example.com", password="correct-horse-battery", display_name="S"
        ),
        request_with_cookie(None),
        response,
        db,
        settings,
    )

    jar = cookies_from(response)
    assert jar[deps.SESSION_COOKIE]["secure"]
    assert jar[deps.CSRF_COOKIE]["secure"]


async def test_login_sets_the_same_cookie_pair(
    db: AsyncSession, settings: Settings
) -> None:
    await AuthService(db, settings).register(
        "loginer@example.com", "correct-horse-battery", "Loginer"
    )
    response = Response()
    await login(
        LoginRequest(email="loginer@example.com", password="correct-horse-battery"),
        request_with_cookie(None),
        response,
        db,
        settings,
    )

    jar = cookies_from(response)
    assert jar[deps.SESSION_COOKIE]["httponly"]
    assert not jar[deps.CSRF_COOKIE]["httponly"]


async def test_refresh_with_no_cookie_is_unauthorized(
    db: AsyncSession, settings: Settings
) -> None:
    with pytest.raises(Unauthorized, match="No session"):
        await refresh(request_with_cookie(None), Response(), db, settings)


async def test_refresh_rotates_the_session_cookie(
    db: AsyncSession, settings: Settings, user: User
) -> None:
    issued = await AuthService(db, settings).issue_session(user)
    response = Response()
    await refresh(request_with_cookie(issued.refresh_token), response, db, settings)

    jar = cookies_from(response)
    assert jar[deps.SESSION_COOKIE].value != issued.refresh_token, (
        "refresh must rotate the token, not reissue the one it was given"
    )
    assert jar[deps.SESSION_COOKIE]["httponly"]


async def test_logout_with_a_cookie_revokes_the_session_and_clears_both_cookies(
    db: AsyncSession, settings: Settings, user: User
) -> None:
    issued = await AuthService(db, settings).issue_session(user)
    response = Response()
    await logout(request_with_cookie(issued.refresh_token), response, db, settings)

    jar = cookies_from(response)
    assert int(jar[deps.SESSION_COOKIE]["max-age"]) == 0
    assert int(jar[deps.CSRF_COOKIE]["max-age"]) == 0

    with pytest.raises(Unauthorized):
        await AuthService(db, settings).refresh(issued.refresh_token)


async def test_logout_with_no_cookie_is_a_noop_that_still_clears_cookies(
    db: AsyncSession, settings: Settings
) -> None:
    response = Response()
    await logout(request_with_cookie(None), response, db, settings)

    jar = cookies_from(response)
    assert int(jar[deps.SESSION_COOKIE]["max-age"]) == 0
    assert int(jar[deps.CSRF_COOKIE]["max-age"]) == 0
