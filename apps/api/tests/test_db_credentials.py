"""BYOK credential storage against a real database.

The property under test is narrow and important: the key goes in, only ``last4``
comes back out, and the ciphertext is useless anywhere but where it was written.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.config import Settings
from noema.core.crypto import EncryptionError, SecretBox
from noema.core.errors import Conflict, NotFound
from noema.db.models import ProviderCredential, User
from noema.services.credentials import CredentialService

API_KEY = "sk-ant-api03-thisisnotarealkey-abcdefghijklmnopqrst"


@pytest.fixture
def box(settings: Settings) -> SecretBox:
    return SecretBox.from_base64(settings.noema_master_key)


@pytest.fixture
def credentials(db: AsyncSession, box: SecretBox, user: User) -> CredentialService:
    return CredentialService(db, box, user.id)


async def test_the_summary_exposes_only_the_last_four(
    credentials: CredentialService,
) -> None:
    summary = await credentials.store("anthropic", "default", API_KEY)

    assert summary.last4 == API_KEY[-4:]
    assert API_KEY not in str(vars(summary))


async def test_the_plaintext_never_reaches_the_database(
    db: AsyncSession, credentials: CredentialService
) -> None:
    await credentials.store("anthropic", "default", API_KEY)

    row = (await db.scalars(select(ProviderCredential))).one()
    for blob in (row.ciphertext, row.wrapped_key, row.nonce, row.wrapped_key_nonce):
        assert API_KEY.encode() not in blob


async def test_the_gateway_can_read_the_key_back(
    credentials: CredentialService,
) -> None:
    await credentials.store("anthropic", "default", API_KEY)
    assert await credentials.reveal_for_gateway("anthropic") == API_KEY


async def test_reading_records_when_the_key_was_last_used(
    credentials: CredentialService,
) -> None:
    summary = await credentials.store("anthropic", "default", API_KEY)
    assert summary.last_used_at is None

    await credentials.reveal_for_gateway("anthropic")

    stored = (await credentials.list())[0]
    assert stored.last_used_at is not None


async def test_a_ciphertext_replanted_under_another_provider_will_not_open(
    db: AsyncSession, credentials: CredentialService
) -> None:
    """The AAD binds each secret to its owner and provider."""
    await credentials.store("anthropic", "default", API_KEY)

    row = (await db.scalars(select(ProviderCredential))).one()
    row.provider = "openai"
    await db.flush()

    with pytest.raises(EncryptionError):
        await credentials.reveal_for_gateway("openai")


async def test_a_ciphertext_replanted_under_another_owner_will_not_open(
    db: AsyncSession, box: SecretBox, credentials: CredentialService, other_user: User
) -> None:
    await credentials.store("anthropic", "default", API_KEY)

    row = (await db.scalars(select(ProviderCredential))).one()
    row.owner_id = other_user.id
    await db.flush()

    with pytest.raises(EncryptionError):
        await CredentialService(db, box, other_user.id).reveal_for_gateway("anthropic")


async def test_missing_credentials_read_as_none_not_an_error(
    credentials: CredentialService,
) -> None:
    assert await credentials.reveal_for_gateway("openai") is None


async def test_duplicate_labels_are_rejected(credentials: CredentialService) -> None:
    await credentials.store("anthropic", "default", API_KEY)
    with pytest.raises(Conflict):
        await credentials.store("anthropic", "default", API_KEY)


async def test_deleting_a_credential_removes_it(
    credentials: CredentialService,
) -> None:
    summary = await credentials.store("anthropic", "default", API_KEY)
    await credentials.delete(summary.id)

    assert await credentials.list() == []
    assert await credentials.reveal_for_gateway("anthropic") is None


async def test_another_users_credential_is_not_reachable(
    db: AsyncSession, box: SecretBox, credentials: CredentialService, other_user: User
) -> None:
    summary = await credentials.store("anthropic", "default", API_KEY)
    mallory = CredentialService(db, box, other_user.id)

    assert await mallory.list() == []
    assert await mallory.reveal_for_gateway("anthropic") is None
    with pytest.raises(NotFound):
        await mallory.delete(summary.id)


async def test_verification_failures_are_recorded_for_the_ui(
    credentials: CredentialService,
) -> None:
    summary = await credentials.store("anthropic", "default", API_KEY)
    failed = await credentials.mark_verified(summary.id, error="401 from provider")

    assert failed.verification_error == "401 from provider"
    assert failed.last_verified_at is None

    passed = await credentials.mark_verified(summary.id)
    assert passed.verification_error is None
    assert passed.last_verified_at is not None
