"""Authentication against a real database.

The interesting cases are the ones that only exist once sessions are persisted:
rotation, reuse detection, and revocation of a whole session family.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.config import Settings
from noema.core.errors import Conflict, FeatureUnavailable, Unauthorized
from noema.db.models import Session, User, Workspace
from noema.services.auth import AuthService

PASSWORD = "correct-horse-battery"


@pytest.fixture
def auth(db: AsyncSession, settings: Settings) -> AuthService:
    return AuthService(db, settings)


async def test_registration_creates_a_workspace_to_land_in(
    db: AsyncSession, auth: AuthService
) -> None:
    """An account with nowhere to put anything is a dead end."""
    user = await auth.register("bob@example.com", PASSWORD, "Bob")

    workspaces = (
        await db.scalars(select(Workspace).where(Workspace.owner_id == user.id))
    ).all()
    assert len(workspaces) == 1


async def test_passwords_are_never_stored_in_the_clear(auth: AuthService) -> None:
    user = await auth.register("carol@example.com", PASSWORD, "Carol")
    assert PASSWORD not in user.password_hash
    assert user.password_hash.startswith("$argon2")


async def test_email_is_normalised(auth: AuthService) -> None:
    user = await auth.register("  DAVE@Example.COM ", PASSWORD, "Dave")
    assert user.email == "dave@example.com"
    assert await auth.authenticate("dave@example.com", PASSWORD)


async def test_duplicate_registration_is_rejected(auth: AuthService) -> None:
    await auth.register("erin@example.com", PASSWORD, "Erin")
    with pytest.raises(Conflict):
        await auth.register("erin@example.com", PASSWORD, "Erin Again")


async def test_signups_can_be_disabled(db: AsyncSession, settings: Settings) -> None:
    settings.noema_allow_signups = False
    with pytest.raises(FeatureUnavailable):
        await AuthService(db, settings).register("frank@example.com", PASSWORD, "Frank")


async def test_wrong_password_and_unknown_email_are_indistinguishable(
    auth: AuthService,
) -> None:
    await auth.register("grace@example.com", PASSWORD, "Grace")

    with pytest.raises(Unauthorized) as wrong_password:
        await auth.authenticate("grace@example.com", "not-the-password")
    with pytest.raises(Unauthorized) as unknown_email:
        await auth.authenticate("nobody@example.com", PASSWORD)

    # Different messages here would be a user-enumeration oracle.
    assert str(wrong_password.value) == str(unknown_email.value)


async def test_a_session_resolves_back_to_its_user(auth: AuthService, user: User) -> None:
    issued = await auth.issue_session(user)
    resolved, session = await auth.resolve(issued.refresh_token)

    assert resolved.id == user.id
    assert session.csrf_token == issued.csrf_token


async def test_the_raw_refresh_token_is_not_stored(
    db: AsyncSession, auth: AuthService, user: User
) -> None:
    issued = await auth.issue_session(user)
    rows = (await db.scalars(select(Session).where(Session.user_id == user.id))).all()

    assert all(row.refresh_token_hash != issued.refresh_token for row in rows)


async def test_refresh_rotates_the_token(auth: AuthService, user: User) -> None:
    first = await auth.issue_session(user)
    second = await auth.refresh(first.refresh_token)

    assert second.refresh_token != first.refresh_token

    # The rotated token is dead on arrival.
    with pytest.raises(Unauthorized):
        await auth.resolve(first.refresh_token)
    assert (await auth.resolve(second.refresh_token))[0].id == user.id


async def test_reusing_a_rotated_token_revokes_the_whole_family(
    auth: AuthService, user: User
) -> None:
    """Reuse means the token leaked. We cannot tell attacker from user, so both go."""
    first = await auth.issue_session(user)
    second = await auth.refresh(first.refresh_token)

    with pytest.raises(Unauthorized, match="revoked"):
        await auth.refresh(first.refresh_token)

    # The legitimate current token is revoked too — that is the point.
    with pytest.raises(Unauthorized):
        await auth.resolve(second.refresh_token)


async def test_an_expired_session_is_refused(
    db: AsyncSession, auth: AuthService, user: User
) -> None:
    from datetime import UTC, datetime, timedelta

    issued = await auth.issue_session(user)
    _, session = await auth.resolve(issued.refresh_token)
    session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db.flush()

    with pytest.raises(Unauthorized):
        await auth.resolve(issued.refresh_token)


async def test_logout_revokes_the_session(auth: AuthService, user: User) -> None:
    issued = await auth.issue_session(user)
    await auth.logout(issued.refresh_token)

    with pytest.raises(Unauthorized):
        await auth.resolve(issued.refresh_token)


async def test_a_deleted_account_cannot_be_resolved(
    db: AsyncSession, auth: AuthService, user: User
) -> None:
    from noema.db.base import utcnow

    issued = await auth.issue_session(user)
    user.deleted_at = utcnow()
    await db.flush()

    with pytest.raises(Unauthorized):
        await auth.resolve(issued.refresh_token)


async def test_an_unknown_token_is_refused(auth: AuthService) -> None:
    with pytest.raises(Unauthorized):
        await auth.resolve("not-a-real-token")
    with pytest.raises(Unauthorized):
        await auth.refresh("not-a-real-token")
