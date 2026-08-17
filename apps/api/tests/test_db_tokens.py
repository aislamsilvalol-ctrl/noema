"""API tokens: the service that stores them, and the deps that check them."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from noema.api.v1 import deps
from noema.core.config import Settings
from noema.core.errors import Forbidden, Unauthorized
from noema.core.security import hash_token
from noema.db.base import utcnow
from noema.db.models import ApiToken, User
from noema.services.auth import AuthService
from noema.services.tokens import (
    TOKEN_PREFIX,
    create_token,
    list_tokens,
    resolve_token,
    revoke_token,
)

pytestmark = pytest.mark.asyncio


def request_for(
    method: str = "GET",
    *,
    bearer: str | None = None,
    cookie: str | None = None,
    csrf_header: str | None = None,
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if bearer is not None:
        headers.append((b"authorization", f"Bearer {bearer}".encode()))
    if csrf_header is not None:
        headers.append((b"x-csrf-token", csrf_header.encode()))
    if cookie is not None:
        headers.append((b"cookie", f"noema_session={cookie}".encode()))

    scope = {
        "type": "http",
        "method": method,
        "path": "/",
        "query_string": b"",
        "headers": headers,
    }
    return Request(scope)


# ── The service ────────────────────────────────────────────────────────────────


async def test_a_created_token_is_never_stored_in_plaintext(
    db: AsyncSession, user: User
) -> None:
    created = await create_token(
        db, owner_id=user.id, name="CI", scopes=["read", "write"]
    )

    assert created.secret.startswith(TOKEN_PREFIX)
    assert created.token.token_hash == hash_token(created.secret)
    assert created.secret not in created.token.token_hash


async def test_list_tokens_excludes_revoked(db: AsyncSession, user: User) -> None:
    kept = await create_token(db, owner_id=user.id, name="Kept", scopes=["read"])
    dropped = await create_token(db, owner_id=user.id, name="Dropped", scopes=["read"])
    await revoke_token(db, owner_id=user.id, token_id=dropped.token.id)

    tokens = await list_tokens(db, owner_id=user.id)

    assert [token.id for token in tokens] == [kept.token.id]


async def test_revoke_token_reports_whether_it_found_one(
    db: AsyncSession, user: User, other_user: User
) -> None:
    created = await create_token(db, owner_id=user.id, name="Mine", scopes=["read"])

    assert await revoke_token(db, owner_id=user.id, token_id=uuid.uuid4()) is False
    assert (
        await revoke_token(db, owner_id=other_user.id, token_id=created.token.id) is False
    )
    assert await revoke_token(db, owner_id=user.id, token_id=created.token.id) is True

    revoked = await db.get(ApiToken, created.token.id)
    assert revoked is not None
    assert revoked.revoked_at is not None


async def test_resolve_token_returns_the_owner_and_scopes(
    db: AsyncSession, user: User
) -> None:
    created = await create_token(
        db, owner_id=user.id, name="CI", scopes=["read", "write"]
    )

    resolved_user, scopes = await resolve_token(db, created.secret)

    assert resolved_user.id == user.id
    assert scopes == ["read", "write"]


async def test_resolve_token_records_last_used_at(db: AsyncSession, user: User) -> None:
    created = await create_token(db, owner_id=user.id, name="CI", scopes=["read"])
    assert created.token.last_used_at is None

    await resolve_token(db, created.secret)

    assert created.token.last_used_at is not None


async def test_resolve_token_rejects_garbage(db: AsyncSession) -> None:
    with pytest.raises(Unauthorized):
        await resolve_token(db, "noema_not-a-real-token")


async def test_resolve_token_rejects_a_revoked_token(
    db: AsyncSession, user: User
) -> None:
    created = await create_token(db, owner_id=user.id, name="CI", scopes=["read"])
    await revoke_token(db, owner_id=user.id, token_id=created.token.id)

    with pytest.raises(Unauthorized):
        await resolve_token(db, created.secret)


async def test_resolve_token_rejects_an_expired_token(
    db: AsyncSession, user: User
) -> None:
    created = await create_token(
        db,
        owner_id=user.id,
        name="CI",
        scopes=["read"],
        expires_at=utcnow() - timedelta(seconds=1),
    )

    with pytest.raises(Unauthorized):
        await resolve_token(db, created.secret)


# ── The FastAPI dependencies that check them ──────────────────────────────────


async def test_a_read_token_may_call_a_safe_method(
    db: AsyncSession, user: User, settings: Settings
) -> None:
    created = await create_token(db, owner_id=user.id, name="CI", scopes=["read"])

    resolved = await deps.get_current_user(
        request_for("GET", bearer=created.secret), db, settings
    )

    assert resolved.id == user.id


async def test_a_read_only_token_may_not_call_a_mutating_method(
    db: AsyncSession, user: User, settings: Settings
) -> None:
    created = await create_token(db, owner_id=user.id, name="CI", scopes=["read"])

    with pytest.raises(Forbidden):
        await deps.get_current_user(
            request_for("POST", bearer=created.secret), db, settings
        )


async def test_a_write_token_may_call_a_mutating_method(
    db: AsyncSession, user: User, settings: Settings
) -> None:
    created = await create_token(db, owner_id=user.id, name="CI", scopes=["write"])

    resolved = await deps.get_current_user(
        request_for("POST", bearer=created.secret), db, settings
    )

    assert resolved.id == user.id


async def test_a_session_cookie_still_authenticates(
    db: AsyncSession, user: User, settings: Settings
) -> None:
    issued = await AuthService(db, settings).issue_session(user)

    resolved = await deps.get_current_user(
        request_for("GET", cookie=issued.refresh_token), db, settings
    )

    assert resolved.id == user.id


async def test_csrf_is_not_required_on_a_bearer_authenticated_mutation(
    db: AsyncSession, user: User, settings: Settings
) -> None:
    created = await create_token(db, owner_id=user.id, name="CI", scopes=["write"])

    await deps.require_csrf(request_for("POST", bearer=created.secret), db, settings)


async def test_csrf_is_still_required_on_a_cookie_authenticated_mutation(
    db: AsyncSession, user: User, settings: Settings
) -> None:
    issued = await AuthService(db, settings).issue_session(user)

    with pytest.raises(Forbidden):
        await deps.require_csrf(
            request_for("POST", cookie=issued.refresh_token), db, settings
        )

    # The matching header makes it through.
    await deps.require_csrf(
        request_for("POST", cookie=issued.refresh_token, csrf_header=issued.csrf_token),
        db,
        settings,
    )


async def test_the_session_only_dependency_rejects_a_bearer_token(
    db: AsyncSession, user: User, settings: Settings
) -> None:
    created = await create_token(db, owner_id=user.id, name="CI", scopes=["write"])

    with pytest.raises(Unauthorized):
        await deps.get_session_user(
            request_for("GET", bearer=created.secret), db, settings
        )
