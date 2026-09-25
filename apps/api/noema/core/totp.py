"""Time-based one-time passwords (RFC 6238), and nothing else.

Thirty lines of standard library rather than a dependency: HOTP is an HMAC
and a truncation, and every authenticator app speaks this exact profile —
SHA-1, six digits, thirty-second steps. Verified against the RFC's own test
vectors in `tests/test_totp.py`.

`verify` returns the time step that matched, so the caller can refuse the same
code twice: a code seen once over someone's shoulder must not work again.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP_SECONDS = 30
DIGITS = 6
#: One step either side: a phone clock thirty seconds off still works.
DRIFT_STEPS = 1


def new_secret() -> str:
    """160 random bits, base32 without padding, as authenticator apps expect."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    padded = secret.upper() + "=" * (-len(secret) % 8)
    return base64.b32decode(padded)


def hotp(key: bytes, counter: int, digits: int = DIGITS, digest: str = "sha1") -> str:
    mac = hmac.new(key, struct.pack(">Q", counter), getattr(hashlib, digest)).digest()
    offset = mac[-1] & 0x0F
    code = struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(code % 10**digits).zfill(digits)


def code_at(secret: str, moment: float) -> str:
    return hotp(_key(secret), int(moment) // STEP_SECONDS)


def verify(
    secret: str, code: str, *, now: float | None = None, after_step: int = -1
) -> int | None:
    """The matching time step, or None. Steps at or before `after_step` never match."""
    code = code.strip().replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return None
    step = int(time.time() if now is None else now) // STEP_SECONDS
    key = _key(secret)
    for candidate in range(step - DRIFT_STEPS, step + DRIFT_STEPS + 1):
        if candidate <= after_step:
            continue
        if hmac.compare_digest(hotp(key, candidate), code):
            return candidate
    return None


def provisioning_uri(secret: str, account: str, issuer: str = "NOEMA") -> str:
    label = quote(f"{issuer}:{account}")
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}"
        f"&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}"
    )
