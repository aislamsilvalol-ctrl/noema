"""Scoped tokens for the public REST API.

A token is a second way in, alongside the cookie session the web app uses —
built to be handed to a script or another service, not typed in by a person, so
it carries no CSRF protection and no refresh: it is either valid or it is
revoked. Scope is checked once, centrally, in `noema.api.v1.deps.get_current_user`
— not per endpoint, so a route added later is scoped by construction rather than
by whoever remembers to add the check.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core import security
from noema.core.errors import Unauthorized
from noema.db.base import utcnow
from noema.db.models import ApiToken, User

__all__ = [
    "SCOPES",
    "TOKEN_PREFIX",
    "CreatedToken",
    "create_token",
    "list_tokens",
    "resolve_token",
    "revoke_token",
]

#: The only scopes v1 has. "write" implies "read" wherever this is checked —
#: there is no operation write cannot do that read also permits.
SCOPES = ("read", "write")

#: Every token is identifiable at a glance, and by a secret scanner's regex —
#: the same reason a hardcoded master key would be flagged, worked backwards.
TOKEN_PREFIX = "noema_"  # noqa: S105 — a prefix, not a credential


@dataclass(frozen=True, slots=True)
class CreatedToken:
    token: ApiToken
    #: Shown exactly once. Nothing after this call can recover it, the same
    #: property `ProviderCredential` has and for the same reason: a database
    #: leak must not be a token leak.
    secret: str


async def create_token(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    name: str,
    scopes: list[str],
    expires_at: datetime | None = None,
) -> CreatedToken:
    secret = TOKEN_PREFIX + security.generate_token()
    token = ApiToken(
        owner_id=owner_id,
        name=name,
        token_hash=security.hash_token(secret),
        scopes=scopes,
        expires_at=expires_at,
    )
    session.add(token)
    await session.flush()
    return CreatedToken(token=token, secret=secret)


async def list_tokens(session: AsyncSession, *, owner_id: uuid.UUID) -> list[ApiToken]:
    rows = await session.execute(
        select(ApiToken)
        .where(ApiToken.owner_id == owner_id, ApiToken.revoked_at.is_(None))
        .order_by(ApiToken.created_at.desc())
    )
    return list(rows.scalars())


async def revoke_token(
    session: AsyncSession, *, owner_id: uuid.UUID, token_id: uuid.UUID
) -> bool:
    """Revoke a token this owner holds. False if there was none to revoke."""
    result = await session.execute(
        update(ApiToken)
        .where(
            ApiToken.id == token_id,
            ApiToken.owner_id == owner_id,
            ApiToken.revoked_at.is_(None),
        )
        .values(revoked_at=utcnow())
    )
    # An UPDATE's Result is a CursorResult at runtime, which has `rowcount`; the
    # static return type of `execute()` does not know that.
    rowcount: int = result.rowcount  # type: ignore[attr-defined]
    return rowcount > 0


async def resolve_token(session: AsyncSession, secret: str) -> tuple[User, list[str]]:
    """The user and scopes for a bearer token, or `Unauthorized`.

    Also records the use — `last_used_at` is what tells an owner a token they
    forgot about is still live, which is the only way they would know to revoke it.
    """
    record = await session.scalar(
        select(ApiToken).where(ApiToken.token_hash == security.hash_token(secret))
    )
    if (
        record is None
        or record.revoked_at is not None
        or (record.expires_at is not None and security.is_expired(record.expires_at))
    ):
        raise Unauthorized("Invalid or expired API token.")

    user = await session.get(User, record.owner_id)
    if user is None or user.deleted_at is not None:
        raise Unauthorized("Account unavailable.")

    record.last_used_at = utcnow()
    return user, record.scopes
