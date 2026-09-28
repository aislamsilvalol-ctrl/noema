"""Email verification against the real tables: the token's life, the
account's flag, and the two routes around them.

NOEMA_RESEND_API_KEY is unset here, so every send hits the unconfigured
branch and is swallowed -- same arrangement as the password-reset tests.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import Response

from noema.api.v1 import auth as auth_routes
from noema.api.v1.schemas import RegisterRequest, UserOut, VerifyEmailRequest
from noema.core import security
from noema.core.config import Settings
from noema.core.errors import LinkExpired, RateLimited, Unauthorized
from noema.db.models import EmailVerificationToken, User
from noema.services.email_verification import EmailVerification

pytestmark = pytest.mark.asyncio


@pytest.fixture
def verification(db: AsyncSession, settings: Settings) -> EmailVerification:
    return EmailVerification(db, settings)


def _request(*, redis: Any | None = None) -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/verify-email/resend",
        "query_string": b"",
        "headers": [],
        "client": ("10.0.0.1", 1234),
    }
    if redis is not None:
        from types import SimpleNamespace

        scope["app"] = SimpleNamespace(state=SimpleNamespace(redis=redis))
    return Request(scope)


async def _tokens(db: AsyncSession, user: User) -> list[EmailVerificationToken]:
    return list(
        (
            await db.scalars(
                select(EmailVerificationToken).where(
                    EmailVerificationToken.user_id == user.id
                )
            )
        ).all()
    )


# ── the account ────────────────────────────────────────────────────────────


async def test_a_new_account_starts_unverified(user: User) -> None:
    assert user.email_verified_at is None
    assert UserOut.model_validate(user).email_verified is False


async def test_registering_issues_a_token_and_queues_the_email(
    db: AsyncSession, settings: Settings
) -> None:
    background = BackgroundTasks()
    out = await auth_routes.register(
        RegisterRequest(
            email="fresh@example.com",
            password="correct-horse-battery",
            display_name="Fresh",
        ),
        _request(),
        Response(),
        db,
        settings,
        background,
    )

    user = await db.get(User, out.user.id)
    assert user is not None
    tokens = await _tokens(db, user)
    assert len(tokens) == 1
    assert tokens[0].used_at is None
    assert not security.is_expired(tokens[0].expires_at)
    # Queued, not sent: the response goes out first.
    assert len(background.tasks) == 1
    assert out.user.email_verified is False


# ── the token ──────────────────────────────────────────────────────────────


async def test_a_valid_token_verifies_the_account_once(
    db: AsyncSession, verification: EmailVerification, user: User
) -> None:
    token = await verification.issue(user)

    verified = await verification.verify(token)

    assert verified.id == user.id
    assert user.email_verified_at is not None
    assert UserOut.model_validate(user).email_verified is True
    (record,) = await _tokens(db, user)
    assert record.used_at is not None

    with pytest.raises(Unauthorized):
        await verification.verify(token)


async def test_an_expired_token_says_so(
    db: AsyncSession, verification: EmailVerification, user: User
) -> None:
    raw = security.generate_token()
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=security.hash_token(raw),
            expires_at=security.expires_in(-1),
        )
    )
    await db.flush()

    with pytest.raises(LinkExpired):
        await verification.verify(raw)
    assert user.email_verified_at is None


async def test_an_unknown_token_is_refused(verification: EmailVerification) -> None:
    with pytest.raises(Unauthorized):
        await verification.verify("not-a-real-token")


async def test_the_first_link_still_works_after_a_resend(
    verification: EmailVerification, user: User
) -> None:
    first = await verification.issue(user)
    await verification.issue(user)

    await verification.verify(first)

    assert user.email_verified_at is not None


async def test_verifying_again_keeps_the_original_date(
    verification: EmailVerification, user: User
) -> None:
    first = await verification.issue(user)
    second = await verification.issue(user)
    await verification.verify(first)
    stamped = user.email_verified_at

    await verification.verify(second)

    assert user.email_verified_at == stamped


async def test_a_deleted_accounts_token_is_refused(
    db: AsyncSession, verification: EmailVerification, user: User
) -> None:
    token = await verification.issue(user)
    from noema.db.base import utcnow

    user.deleted_at = utcnow()
    await db.flush()

    with pytest.raises(Unauthorized):
        await verification.verify(token)


# ── the routes ─────────────────────────────────────────────────────────────


async def test_the_verify_route_marks_the_account(
    db: AsyncSession, settings: Settings, verification: EmailVerification, user: User
) -> None:
    token = await verification.issue(user)

    await auth_routes.verify_email(VerifyEmailRequest(token=token), db, settings)

    assert user.email_verified_at is not None


async def test_resend_issues_a_new_token_for_an_unverified_account(
    db: AsyncSession, settings: Settings, user: User
) -> None:
    background = BackgroundTasks()

    await auth_routes.resend_verification(_request(), user, background, db, settings)

    assert len(await _tokens(db, user)) == 1
    assert len(background.tasks) == 1


async def test_resend_is_a_no_op_once_verified(
    db: AsyncSession, settings: Settings, verification: EmailVerification, user: User
) -> None:
    await verification.verify(await verification.issue(user))
    background = BackgroundTasks()

    await auth_routes.resend_verification(_request(), user, background, db, settings)

    assert len(await _tokens(db, user)) == 1
    assert background.tasks == []


async def test_resend_is_throttled_per_account(
    db: AsyncSession, settings: Settings, user: User, other_user: User
) -> None:
    class ClaimingRedis:
        def __init__(self) -> None:
            self.keys: set[str] = set()

        async def set(self, key: str, value: int, *, nx: bool, ex: int) -> bool | None:
            if key in self.keys:
                return None
            self.keys.add(key)
            return True

    redis = ClaimingRedis()

    await auth_routes.resend_verification(
        _request(redis=redis), user, BackgroundTasks(), db, settings
    )
    with pytest.raises(RateLimited) as caught:
        await auth_routes.resend_verification(
            _request(redis=redis), user, BackgroundTasks(), db, settings
        )
    assert caught.value.extra["retry_after"] > 0
    # Another account is another key.
    await auth_routes.resend_verification(
        _request(redis=redis), other_user, BackgroundTasks(), db, settings
    )

    assert len(await _tokens(db, user)) == 1
    assert len(await _tokens(db, other_user)) == 1
