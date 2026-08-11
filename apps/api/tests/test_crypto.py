from __future__ import annotations

import base64
import os

import pytest

from noema.core.crypto import EncryptionError, SecretBox, last4

KEY = base64.b64encode(os.urandom(32)).decode()
SECRET = "sk-ant-api03-notarealkey-abcdefghijklmnop"


@pytest.fixture
def box() -> SecretBox:
    return SecretBox.from_base64(KEY)


def test_round_trip(box: SecretBox) -> None:
    sealed = box.seal(SECRET)
    assert box.open(sealed) == SECRET


def test_ciphertext_never_contains_the_plaintext(box: SecretBox) -> None:
    sealed = box.seal(SECRET)
    for blob in (sealed.ciphertext, sealed.wrapped_key, sealed.nonce):
        assert SECRET.encode() not in blob


def test_same_plaintext_seals_differently_each_time(box: SecretBox) -> None:
    """Deterministic ciphertext would leak which users share a key."""
    first, second = box.seal(SECRET), box.seal(SECRET)
    assert first.ciphertext != second.ciphertext
    assert first.wrapped_key != second.wrapped_key


def test_aad_binds_the_secret_to_its_context(box: SecretBox) -> None:
    """A ciphertext replanted under another owner or provider must not decrypt."""
    sealed = box.seal(SECRET, aad=b"user-a:anthropic")
    assert box.open(sealed, aad=b"user-a:anthropic") == SECRET
    with pytest.raises(EncryptionError):
        box.open(sealed, aad=b"user-b:anthropic")
    with pytest.raises(EncryptionError):
        box.open(sealed, aad=b"user-a:openai")


def test_another_master_key_cannot_open_it(box: SecretBox) -> None:
    sealed = box.seal(SECRET)
    other = SecretBox.from_base64(base64.b64encode(os.urandom(32)).decode())
    with pytest.raises(EncryptionError):
        other.open(sealed)


def test_tampering_is_detected(box: SecretBox) -> None:
    sealed = box.seal(SECRET)
    flipped = bytearray(sealed.ciphertext)
    flipped[0] ^= 0x01
    from dataclasses import replace

    with pytest.raises(EncryptionError):
        box.open(replace(sealed, ciphertext=bytes(flipped)))


def test_rewrap_rotates_the_master_key_without_touching_the_payload(
    box: SecretBox,
) -> None:
    sealed = box.seal(SECRET)
    new_box = SecretBox.from_base64(base64.b64encode(os.urandom(32)).decode())

    rotated = box.rewrap(sealed, new_box)

    assert rotated.ciphertext == sealed.ciphertext  # payload untouched
    assert rotated.key_version == sealed.key_version + 1
    assert new_box.open(rotated) == SECRET
    with pytest.raises(EncryptionError):
        box.open(rotated)


def test_placeholder_master_key_is_refused() -> None:
    with pytest.raises(EncryptionError, match="not configured"):
        SecretBox.from_base64("CHANGE_ME_base64_32_bytes")
    with pytest.raises(EncryptionError, match="not configured"):
        SecretBox.from_base64("")


def test_wrong_length_master_key_is_refused() -> None:
    with pytest.raises(EncryptionError):
        SecretBox.from_base64(base64.b64encode(os.urandom(16)).decode())


def test_last4_is_all_we_ever_expose() -> None:
    assert last4(SECRET) == SECRET[-4:]
    assert last4("ab") == "****"
