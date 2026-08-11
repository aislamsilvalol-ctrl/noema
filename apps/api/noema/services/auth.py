"""Authentication: registration, login, refresh rotation, revocation.

Refresh tokens rotate on every use and are stored hashed. Presenting an already-used
token means it leaked, so the entire session family is revoked rather than the single
token — the attacker and the legitimate user both get logged out, which is the
correct outcome when you cannot tell them apart.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core import security
from noema.core.config import Settings
from noema.core.errors import Conflict, FeatureUnavailable, Unauthorized
from noema.core.logging import get_logger
from noema.db.base import utcnow
from noema.db.models import Session, User, Workspace

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class IssuedSession:
    refresh_token: str
    csrf_token: str
    expires_at: datetime
    user: User


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.db = session
        self.settings = settings

    async def register(
        self, email: str, password: str, display_name: str
    ) -> User:
        if not self.settings.noema_allow_signups:
            raise FeatureUnavailable("Registration is disabled on this deployment.")

        email = email.strip().lower()
        existing = await self.db.scalar(select(User).where(User.email == email))
        if existing is not None:
            raise Conflict("An account with that email already exists.")

        user = User(
            email=email,
            password_hash=security.hash_password(password),
            display_name=display_name.strip() or email.split("@")[0],
            settings={},
        )
        self.db.add(user)
        await self.db.flush()

        # A workspace with nothing in it is a dead end. Give every new account one
        # place to put something.
        self.db.add(
            Workspace(owner_id=user.id, title="My Workspace", slug="my-workspace", position=0)
        )
        await self.db.flush()
        return user

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.db.scalar(
            select(User).where(User.email == email.strip().lower(), User.deleted_at.is_(None))
        )
        if user is None:
            # Hash anyway: a fast "no such user" response is a user enumeration oracle.
            security.hash_password(password)
            raise Unauthorized("Invalid email or password.")

        if not security.verify_password(password, user.password_hash):
            raise Unauthorized("Invalid email or password.")

        if security.needs_rehash(user.password_hash):
            user.password_hash = security.hash_password(password)
            await self.db.flush()

        return user

    async def issue_session(
        self,
        user: User,
        *,
        family_id: uuid.UUID | None = None,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> IssuedSession:
        refresh_token = security.generate_token()
        csrf_token = security.generate_csrf_token()
        expires_at = security.expires_in(self.settings.refresh_token_ttl_seconds)

        self.db.add(
            Session(
                user_id=user.id,
                family_id=family_id or uuid.uuid4(),
                refresh_token_hash=security.hash_token(refresh_token),
                csrf_token=csrf_token,
                expires_at=expires_at,
                user_agent=(user_agent or "")[:400] or None,
                ip_hash=hashlib.sha256(ip.encode()).hexdigest() if ip else None,
            )
        )
        await self.db.flush()
        return IssuedSession(refresh_token, csrf_token, expires_at, user)

    async def refresh(self, refresh_token: str, **context: str | None) -> IssuedSession:
        token_hash = security.hash_token(refresh_token)
        record = await self.db.scalar(
            select(Session).where(Session.refresh_token_hash == token_hash)
        )
        if record is None:
            raise Unauthorized("Invalid session.")

        if record.revoked_at is not None:
            # Reuse of a rotated token: the family is compromised.
            await self._revoke_family(record.family_id)
            log.warning("auth.refresh_reuse_detected", family_id=str(record.family_id))
            raise Unauthorized("Session revoked. Please sign in again.")

        if security.is_expired(record.expires_at):
            raise Unauthorized("Session expired.")

        user = await self.db.get(User, record.user_id)
        if user is None or user.deleted_at is not None:
            raise Unauthorized("Account unavailable.")

        record.revoked_at = utcnow()
        await self.db.flush()
        return await self.issue_session(
            user,
            family_id=record.family_id,
            user_agent=context.get("user_agent"),
            ip=context.get("ip"),
        )

    async def resolve(self, refresh_token: str) -> tuple[User, Session]:
        """Load the user for an active session token."""
        record = await self.db.scalar(
            select(Session).where(
                Session.refresh_token_hash == security.hash_token(refresh_token),
                Session.revoked_at.is_(None),
            )
        )
        if record is None or security.is_expired(record.expires_at):
            raise Unauthorized("Not authenticated.")

        user = await self.db.get(User, record.user_id)
        if user is None or user.deleted_at is not None:
            raise Unauthorized("Account unavailable.")
        return user, record

    async def logout(self, refresh_token: str) -> None:
        await self.db.execute(
            update(Session)
            .where(Session.refresh_token_hash == security.hash_token(refresh_token))
            .values(revoked_at=utcnow())
        )

    async def _revoke_family(self, family_id: uuid.UUID) -> None:
        await self.db.execute(
            update(Session)
            .where(Session.family_id == family_id, Session.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
