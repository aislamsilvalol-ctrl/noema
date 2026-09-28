"""Proving an account can read its own inbox.

A link goes out at registration (and again on request); opening it stamps
`users.email_verified_at`. The token is the password-reset token's twin --
hashed at rest, single use, expiring -- with a longer life, because the
worst it can do is confirm an address its holder already reads.

The row is written inside the request; only the email leaves in a
background task, the way security receipts do. Mail that never arrives
does not fail a registration, and the learner can ask for another.

Portuguese only, the same known limitation as the reset email: the
backend has no reliable signal for a user's locale, and Portuguese
matches this deployment's real userbase rather than guessing.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core import security
from noema.core.config import Settings
from noema.core.errors import LinkExpired, Unauthorized
from noema.core.logging import get_logger
from noema.db.base import utcnow
from noema.db.models import EmailVerificationToken, User
from noema.services.email import send_email

log = get_logger(__name__)

INVALID = "This verification link is invalid or has already been used."
EXPIRED = "This verification link has expired. Ask for a new one."


class EmailVerification:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.db = session
        self.settings = settings

    async def issue(self, user: User) -> str:
        """A fresh token for this account, returned raw for the link and
        stored hashed. Earlier links stay valid until they expire: the one
        the learner finally opens may be the first email, not the last."""
        token = security.generate_token()
        self.db.add(
            EmailVerificationToken(
                user_id=user.id,
                token_hash=security.hash_token(token),
                expires_at=security.expires_in(
                    self.settings.noema_email_verification_ttl_seconds
                ),
            )
        )
        await self.db.flush()
        return token

    async def verify(self, token: str) -> User:
        # Row-locked for the rest of the transaction, as in `reset_password`:
        # two clicks on the same link must not both consume it.
        record = await self.db.scalar(
            select(EmailVerificationToken)
            .where(EmailVerificationToken.token_hash == security.hash_token(token))
            .with_for_update()
        )
        if record is None or record.used_at is not None:
            raise Unauthorized(INVALID)
        if security.is_expired(record.expires_at):
            raise LinkExpired(EXPIRED)

        user = await self.db.get(User, record.user_id)
        if user is None or user.deleted_at is not None:
            raise Unauthorized(INVALID)

        now = utcnow()
        record.used_at = now
        # An account verified by an earlier link keeps its earlier date.
        if user.email_verified_at is None:
            user.email_verified_at = now
        await self.db.flush()
        return user


def verification_link(settings: Settings, token: str) -> str:
    return f"{settings.web_origin()}/verify-email?token={token}"


async def send_verification_email(settings: Settings, email: str, token: str) -> None:
    """The background half. Never raises: the account exists whether or not
    the mail does, and the learner has a resend button."""
    try:
        await send_email(
            settings,
            to=email,
            subject="Confirme seu e-mail no Noema",
            html=_html(verification_link(settings, token)),
        )
    except Exception as exc:
        # The type, not the message: a provider's error text can quote the
        # recipient address.
        log.warning("email_verification.send_failed", error=type(exc).__name__)


def _html(link: str) -> str:
    return f"""
    <p>Bem-vindo ao Noema. Falta só confirmar que este e-mail é seu.</p>
    <p><a href="{link}">Confirmar meu e-mail</a></p>
    <p>Esse link vale por dois dias. Se você não criou uma conta no Noema,
    pode ignorar este email -- nada acontece sem o clique.</p>
    """.strip()
