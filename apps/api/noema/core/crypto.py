"""Envelope encryption for user-supplied API keys.

Each secret gets a fresh data key; the data key is wrapped by the deployment's master
key. That keeps rotation cheap (rewrap, don't re-encrypt) and limits the blast radius
of any single leaked ciphertext.

Nothing here ever returns to a response schema — see ``docs/ai-providers.md`` §5.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Final

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from noema.core.errors import NoemaError

KEY_SIZE: Final = 32
NONCE_SIZE: Final = 12
CURRENT_KEY_VERSION: Final = 1


class EncryptionError(NoemaError):
    slug = "encryption-failed"
    title = "Encryption failed"
    status_code = 500


@dataclass(frozen=True, slots=True)
class SealedSecret:
    """A wrapped data key plus the payload it encrypts."""

    wrapped_key: bytes
    wrapped_key_nonce: bytes
    ciphertext: bytes
    nonce: bytes
    key_version: int = CURRENT_KEY_VERSION


class SecretBox:
    """Seals and opens secrets under a master key.

    The master key comes from ``NOEMA_MASTER_KEY`` (or a KMS in hosted deployments).
    Lose it and stored API keys are unrecoverable — which is the intended property,
    and why ``docs/self-hosting.md`` tells operators to back it up separately.
    """

    def __init__(self, master_key: bytes) -> None:
        if len(master_key) != KEY_SIZE:
            raise EncryptionError(f"master key must be {KEY_SIZE} bytes")
        self._aead = AESGCM(master_key)

    @classmethod
    def from_base64(cls, encoded: str) -> SecretBox:
        if not encoded or encoded.startswith("CHANGE_ME"):
            raise EncryptionError(
                "NOEMA_MASTER_KEY is not configured. Generate one with:\n"
                '  python -c "import os,base64;'
                'print(base64.b64encode(os.urandom(32)).decode())"'
            )
        try:
            return cls(base64.b64decode(encoded, validate=True))
        except EncryptionError:
            raise
        except Exception as exc:
            raise EncryptionError("NOEMA_MASTER_KEY is not valid base64") from exc

    def seal(self, plaintext: str, *, aad: bytes = b"") -> SealedSecret:
        data_key = os.urandom(KEY_SIZE)
        nonce = os.urandom(NONCE_SIZE)
        ciphertext = AESGCM(data_key).encrypt(nonce, plaintext.encode(), aad)

        wrap_nonce = os.urandom(NONCE_SIZE)
        wrapped_key = self._aead.encrypt(wrap_nonce, data_key, aad)

        return SealedSecret(
            wrapped_key=wrapped_key,
            wrapped_key_nonce=wrap_nonce,
            ciphertext=ciphertext,
            nonce=nonce,
        )

    def open(self, sealed: SealedSecret, *, aad: bytes = b"") -> str:
        try:
            data_key = self._aead.decrypt(
                sealed.wrapped_key_nonce, sealed.wrapped_key, aad
            )
            return AESGCM(data_key).decrypt(sealed.nonce, sealed.ciphertext, aad).decode()
        except Exception as exc:
            # Deliberately opaque: a decryption failure must not reveal whether the
            # master key, the AAD, or the ciphertext is the mismatched part.
            raise EncryptionError("could not decrypt secret") from exc

    def rewrap(
        self, sealed: SealedSecret, new_box: SecretBox, *, aad: bytes = b""
    ) -> SealedSecret:
        """Re-encrypt under a new master key without touching the payload."""
        data_key = self._aead.decrypt(sealed.wrapped_key_nonce, sealed.wrapped_key, aad)
        wrap_nonce = os.urandom(NONCE_SIZE)
        return SealedSecret(
            wrapped_key=new_box._aead.encrypt(wrap_nonce, data_key, aad),
            wrapped_key_nonce=wrap_nonce,
            ciphertext=sealed.ciphertext,
            nonce=sealed.nonce,
            key_version=sealed.key_version + 1,
        )


def last4(secret: str) -> str:
    """The only part of a key that may ever leave the server."""
    return secret[-4:] if len(secret) >= 4 else "****"
