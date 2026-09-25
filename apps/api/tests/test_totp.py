"""RFC 6238 appendix B vectors, and the replay rule."""

from __future__ import annotations

import pytest

from noema.core import totp

RFC_KEY = b"12345678901234567890"


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (59, "94287082"),
        (1111111109, "07081804"),
        (1111111111, "14050471"),
        (1234567890, "89005924"),
        (2000000000, "69279037"),
        (20000000000, "65353130"),
    ],
)
def test_the_rfc_vectors(moment: int, expected: str) -> None:
    assert totp.hotp(RFC_KEY, moment // 30, digits=8) == expected


def test_a_fresh_code_verifies_and_the_same_code_does_not_verify_twice() -> None:
    secret = totp.new_secret()
    now = 1_790_000_000.0
    code = totp.code_at(secret, now)

    step = totp.verify(secret, code, now=now)

    assert step is not None
    assert totp.verify(secret, code, now=now, after_step=step) is None


def test_a_phone_thirty_seconds_off_still_works_but_not_two_minutes() -> None:
    secret = totp.new_secret()
    now = 1_790_000_000.0
    assert totp.verify(secret, totp.code_at(secret, now - 30), now=now) is not None
    assert totp.verify(secret, totp.code_at(secret, now - 120), now=now) is None


def test_junk_is_refused_without_raising() -> None:
    secret = totp.new_secret()
    for junk in ["", "12345", "abcdef", "1234567"]:
        assert totp.verify(secret, junk) is None


def test_the_uri_is_what_authenticator_apps_read() -> None:
    uri = totp.provisioning_uri("JBSWY3DPEHPK3PXP", "ana@example.com")
    assert uri.startswith(
        "otpauth://totp/NOEMA%3Aana%40example.com?secret=JBSWY3DPEHPK3PXP"
    )
    assert "issuer=NOEMA" in uri and "period=30" in uri
