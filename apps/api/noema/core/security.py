"""Password hashing, session tokens and CSRF.

Refresh tokens are stored hashed and rotate on every use. A replayed refresh token
means the token was stolen, so the whole session family is revoked rather than the
single token — see ``detect_reuse`` in the auth service.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# OWASP-recommended baseline; raise on hardware that can afford it.
_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=4)

TOKEN_BYTES = 32


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False
    return True


def needs_rehash(password_hash: str) -> bool:
    """True when the stored hash predates a parameter increase."""
    return _hasher.check_needs_rehash(password_hash)


def generate_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    """Session tokens are stored hashed, so a database leak is not a session leak.

    SHA-256 rather than argon2 is correct here: the input is already 256 bits of
    entropy, so there is nothing to brute-force and lookups stay fast.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def expires_in(seconds: int) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=seconds)


def is_expired(moment: datetime) -> bool:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment <= datetime.now(UTC)


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)
