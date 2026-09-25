"""Two-step verification: an authenticator app, recovery codes, challenges.

The flow a learner sees: in Settings, confirm the password, scan a QR code,
type the first code, keep ten recovery codes. From then on a correct password
is only half of signing in; the other half is a code from the phone, or one
recovery code when the phone is gone.

What makes it hold:
- the TOTP secret is sealed (AES-GCM envelope, user id as associated data);
- a code is accepted once: the matched time step is stored and every step at
  or before it is refused, so a code read over a shoulder is already spent;
- recovery codes are stored as SHA-256 of 50 random bits each and burn on use;
- a sign-in challenge lives five minutes, is single use, and allows five
  guesses, so the million six-digit codes are never in reach.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta

import segno
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core import security, totp
from noema.core.crypto import SealedSecret, SecretBox
from noema.core.errors import Conflict, Unauthorized, WrongPassword
from noema.core.logging import get_logger
from noema.db.base import utcnow
from noema.db.models import MfaChallenge, MfaFactor, MfaRecoveryCode, User

log = get_logger(__name__)

RECOVERY_CODES = 10
CHALLENGE_TTL = timedelta(minutes=5)
CHALLENGE_ATTEMPTS = 5
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o, 1/l/i: read aloud, typed back


@dataclass(frozen=True, slots=True)
class Setup:
    secret: str
    uri: str
    qr_svg: str


def _normalise_recovery(code: str) -> str:
    return code.strip().lower().replace("-", "").replace(" ", "")


def _new_recovery_code() -> str:
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(10))
    return f"{raw[:5]}-{raw[5:]}"


class MfaService:
    def __init__(self, db: AsyncSession, box: SecretBox | None) -> None:
        self.db = db
        self.box = box

    # ── State ────────────────────────────────────────────────────────────

    async def factor(self, user_id: uuid.UUID) -> MfaFactor | None:
        found: MfaFactor | None = await self.db.scalar(
            select(MfaFactor).where(MfaFactor.user_id == user_id)
        )
        return found

    async def enabled(self, user_id: uuid.UUID) -> bool:
        factor = await self.factor(user_id)
        return factor is not None and factor.confirmed_at is not None

    async def recovery_codes_left(self, user_id: uuid.UUID) -> int:
        count = await self.db.scalar(
            select(func.count())
            .select_from(MfaRecoveryCode)
            .where(MfaRecoveryCode.user_id == user_id, MfaRecoveryCode.used_at.is_(None))
        )
        return int(count or 0)

    # ── Setup ────────────────────────────────────────────────────────────

    async def begin(self, user: User) -> Setup:
        """A fresh secret waiting for its first code. Replaces an unfinished one."""
        existing = await self.factor(user.id)
        if existing is not None and existing.confirmed_at is not None:
            raise Conflict("Two-step verification is already on.")
        if existing is not None:
            await self.db.delete(existing)
            await self.db.flush()

        if self.box is None:
            raise RuntimeError("MfaService needs the secret box to store a factor")
        secret = totp.new_secret()
        sealed = self.box.seal(secret, aad=user.id.bytes)
        self.db.add(
            MfaFactor(
                user_id=user.id,
                ciphertext=sealed.ciphertext,
                nonce=sealed.nonce,
                wrapped_key=sealed.wrapped_key,
                wrapped_key_nonce=sealed.wrapped_key_nonce,
                key_version=sealed.key_version,
            )
        )
        await self.db.flush()
        uri = totp.provisioning_uri(secret, user.email)
        svg = segno.make(uri, error="m").svg_inline(scale=5, border=2)
        return Setup(secret=secret, uri=uri, qr_svg=svg)

    async def confirm(self, user: User, code: str) -> list[str]:
        """The first code turns it on; the recovery codes come back once."""
        factor = await self.factor(user.id)
        if factor is None:
            raise Conflict("Start the setup again.")
        if factor.confirmed_at is not None:
            raise Conflict("Two-step verification is already on.")
        step = totp.verify(self._secret(user, factor), code, after_step=factor.last_step)
        if step is None:
            raise WrongPassword("That code is not right.")
        factor.last_step = step
        factor.confirmed_at = utcnow()
        codes = await self._replace_recovery_codes(user.id)
        log.info("security.mfa_enabled", user_id=str(user.id))
        return codes

    async def disable(self, user: User, code: str) -> None:
        if not await self.verify(user, code):
            raise WrongPassword("That code is not right.")
        await self.db.execute(delete(MfaFactor).where(MfaFactor.user_id == user.id))
        await self.db.execute(
            delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id)
        )
        await self.db.flush()
        log.info("security.mfa_disabled", user_id=str(user.id))

    async def regenerate_codes(self, user: User) -> list[str]:
        if not await self.enabled(user.id):
            raise Conflict("Two-step verification is off.")
        codes = await self._replace_recovery_codes(user.id)
        log.info("security.mfa_codes_regenerated", user_id=str(user.id))
        return codes

    # ── Verification ─────────────────────────────────────────────────────

    async def verify(self, user: User, code: str) -> bool:
        """An authenticator code, or one unused recovery code. Each works once."""
        factor = await self.db.scalar(
            select(MfaFactor).where(MfaFactor.user_id == user.id).with_for_update()
        )
        if factor is None or factor.confirmed_at is None:
            return False
        step = totp.verify(self._secret(user, factor), code, after_step=factor.last_step)
        if step is not None:
            factor.last_step = step
            await self.db.flush()
            return True

        normalised = _normalise_recovery(code)
        if len(normalised) != 10:
            return False
        result = await self.db.execute(
            update(MfaRecoveryCode)
            .where(
                MfaRecoveryCode.user_id == user.id,
                MfaRecoveryCode.code_hash == security.hash_token(normalised),
                MfaRecoveryCode.used_at.is_(None),
            )
            .values(used_at=utcnow())
        )
        used = bool(getattr(result, "rowcount", 0))
        if used:
            log.info("security.mfa_recovery_code_used", user_id=str(user.id))
        return used

    async def open_challenge(self, user: User) -> str:
        token = security.generate_token()
        self.db.add(
            MfaChallenge(
                user_id=user.id,
                token_hash=security.hash_token(token),
                expires_at=utcnow() + CHALLENGE_TTL,
            )
        )
        await self.db.flush()
        return token

    async def answer_challenge(self, token: str, code: str) -> User:
        """The second step of a sign-in: the user it was for, or a refusal."""
        challenge = await self.db.scalar(
            select(MfaChallenge)
            .where(MfaChallenge.token_hash == security.hash_token(token))
            .with_for_update()
        )
        if (
            challenge is None
            or challenge.used_at is not None
            or security.is_expired(challenge.expires_at)
            or challenge.attempts >= CHALLENGE_ATTEMPTS
        ):
            raise Unauthorized("This sign-in expired. Enter your password again.")
        user = await self.db.get(User, challenge.user_id)
        if user is None or user.deleted_at is not None:
            raise Unauthorized("This sign-in expired. Enter your password again.")

        challenge.attempts += 1
        if not await self.verify(user, code):
            # Committed here, before raising: the request's session rolls back
            # on any exception, and an attempt that rolls back was never
            # counted. Five guesses would become unlimited.
            await self.db.commit()
            log.info("security.mfa_failed", user_id=str(user.id))
            raise WrongPassword("That code is not right.")
        challenge.used_at = utcnow()
        await self.db.flush()
        return user

    # ── Internals ────────────────────────────────────────────────────────

    def _secret(self, user: User, factor: MfaFactor) -> str:
        if self.box is None:
            raise RuntimeError("MfaService needs the secret box to read a factor")
        return self.box.open(
            SealedSecret(
                wrapped_key=factor.wrapped_key,
                wrapped_key_nonce=factor.wrapped_key_nonce,
                ciphertext=factor.ciphertext,
                nonce=factor.nonce,
                key_version=factor.key_version,
            ),
            aad=user.id.bytes,
        )

    async def _replace_recovery_codes(self, user_id: uuid.UUID) -> list[str]:
        await self.db.execute(
            delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user_id)
        )
        codes = [_new_recovery_code() for _ in range(RECOVERY_CODES)]
        for code in codes:
            self.db.add(
                MfaRecoveryCode(
                    user_id=user_id,
                    code_hash=security.hash_token(_normalise_recovery(code)),
                )
            )
        await self.db.flush()
        return codes
