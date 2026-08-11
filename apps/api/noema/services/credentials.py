"""BYOK credential storage.

The public surface of this module returns :class:`CredentialSummary`, which has no
field capable of carrying a key. Plaintext exists only inside :meth:`reveal_for_gateway`,
which is called by the gateway and by nothing else.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.crypto import SealedSecret, SecretBox, last4
from noema.core.errors import Conflict, NotFound
from noema.db.base import utcnow
from noema.db.models import ProviderCredential


@dataclass(frozen=True, slots=True)
class CredentialSummary:
    """Everything the API is allowed to say about a stored key."""

    id: uuid.UUID
    provider: str
    label: str
    last4: str
    created_at: datetime
    last_used_at: datetime | None
    last_verified_at: datetime | None
    verification_error: str | None


class CredentialService:
    def __init__(
        self, session: AsyncSession, box: SecretBox, owner_id: uuid.UUID
    ) -> None:
        self.db = session
        self.box = box
        self.owner_id = owner_id

    def _aad(self, provider: str) -> bytes:
        """Bind ciphertext to its owner and provider.

        Without this, a stolen ciphertext row could be replanted under another
        account or provider and would still decrypt.
        """
        return f"{self.owner_id}:{provider}".encode()

    async def store(self, provider: str, label: str, api_key: str) -> CredentialSummary:
        existing = await self.db.scalar(
            select(ProviderCredential).where(
                ProviderCredential.owner_id == self.owner_id,
                ProviderCredential.provider == provider,
                ProviderCredential.label == label,
            )
        )
        if existing is not None:
            raise Conflict(f"A {provider} key labelled {label!r} already exists.")

        sealed = self.box.seal(api_key, aad=self._aad(provider))
        credential = ProviderCredential(
            owner_id=self.owner_id,
            provider=provider,
            label=label,
            last4=last4(api_key),
            ciphertext=sealed.ciphertext,
            nonce=sealed.nonce,
            wrapped_key=sealed.wrapped_key,
            wrapped_key_nonce=sealed.wrapped_key_nonce,
            key_version=sealed.key_version,
        )
        self.db.add(credential)
        await self.db.flush()
        return _summarize(credential)

    async def list(self) -> list[CredentialSummary]:
        rows = await self.db.scalars(
            select(ProviderCredential)
            .where(ProviderCredential.owner_id == self.owner_id)
            .order_by(ProviderCredential.created_at)
        )
        return [_summarize(row) for row in rows]

    async def delete(self, credential_id: uuid.UUID) -> None:
        credential = await self._get(credential_id)
        await self.db.delete(credential)
        await self.db.flush()

    async def reveal_for_gateway(self, provider: str) -> str | None:
        """Decrypt a key for an outbound provider call. Gateway use only."""
        credential = await self.db.scalar(
            select(ProviderCredential)
            .where(
                ProviderCredential.owner_id == self.owner_id,
                ProviderCredential.provider == provider,
            )
            .order_by(ProviderCredential.created_at.desc())
            .limit(1)
        )
        if credential is None:
            return None

        plaintext = self.box.open(
            SealedSecret(
                wrapped_key=credential.wrapped_key,
                wrapped_key_nonce=credential.wrapped_key_nonce,
                ciphertext=credential.ciphertext,
                nonce=credential.nonce,
                key_version=credential.key_version,
            ),
            aad=self._aad(provider),
        )
        credential.last_used_at = utcnow()
        await self.db.flush()
        return plaintext

    async def mark_verified(
        self, credential_id: uuid.UUID, *, error: str | None = None
    ) -> CredentialSummary:
        credential = await self._get(credential_id)
        credential.verification_error = error
        if error is None:
            credential.last_verified_at = utcnow()
        await self.db.flush()
        return _summarize(credential)

    async def _get(self, credential_id: uuid.UUID) -> ProviderCredential:
        credential = await self.db.scalar(
            select(ProviderCredential).where(
                ProviderCredential.id == credential_id,
                ProviderCredential.owner_id == self.owner_id,
            )
        )
        if credential is None:
            raise NotFound("Credential not found")
        return credential


def _summarize(credential: ProviderCredential) -> CredentialSummary:
    return CredentialSummary(
        id=credential.id,
        provider=credential.provider,
        label=credential.label,
        last4=credential.last4,
        created_at=credential.created_at,
        last_used_at=credential.last_used_at,
        last_verified_at=credential.last_verified_at,
        verification_error=credential.verification_error,
    )
