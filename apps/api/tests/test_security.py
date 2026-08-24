"""`noema/core/security.py` — password hashing, token handling, CSRF, expiry.

Pure functions, no database: everything here is unit-testable directly, and every
one of them is a real security decision (constant-time comparison, transparent
rehash-on-login, tokens stored hashed) rather than a convenience wrapper. Nothing
in this module had a dedicated test before — the auth flows that use it are well
covered end to end (`test_db_auth.py`), but end-to-end coverage doesn't pin down
*why* a malformed hash fails closed, or that a weaker-parameter hash actually gets
flagged for rehash, the way a direct test does.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher

from noema.core import security


def test_a_hashed_password_is_not_the_password_and_verifies_correctly() -> None:
    hashed = security.hash_password("correct-horse-battery")

    assert hashed != "correct-horse-battery"
    assert hashed.startswith("$argon2id$")
    assert security.verify_password("correct-horse-battery", hashed)


def test_verify_password_rejects_a_wrong_password() -> None:
    hashed = security.hash_password("correct-horse-battery")

    assert not security.verify_password("wrong-password", hashed)


def test_verify_password_fails_closed_on_a_malformed_hash() -> None:
    """`argon2.verify` raises `InvalidHashError` on garbage input — a corrupt or
    truncated stored hash must read as "does not match", never propagate."""
    assert not security.verify_password("anything", "not-an-argon2-hash")


def test_needs_rehash_is_false_for_a_hash_from_current_parameters() -> None:
    hashed = security.hash_password("correct-horse-battery")

    assert not security.needs_rehash(hashed)


def test_needs_rehash_flags_a_hash_from_weaker_parameters() -> None:
    """The rehash-on-login path only does anything if this actually catches a
    hash made under a since-raised cost setting."""
    weaker = PasswordHasher(time_cost=1, memory_cost=8 * 1024, parallelism=1)
    stale_hash = weaker.hash("correct-horse-battery")

    assert security.needs_rehash(stale_hash)
    # And the weaker hash still verifies — rehashing is a maintenance step, not
    # a reason the old hash should ever stop working on its own.
    assert security.verify_password("correct-horse-battery", stale_hash)


def test_generate_token_is_url_safe_and_unique_per_call() -> None:
    a = security.generate_token()
    b = security.generate_token()

    assert a != b
    assert len(a) > 32
    assert all(c.isalnum() or c in "-_" for c in a), (
        "must survive a Set-Cookie header unescaped"
    )


def test_hash_token_is_deterministic_and_does_not_reveal_the_token() -> None:
    token = security.generate_token()

    digest = security.hash_token(token)

    assert digest == security.hash_token(token)
    assert digest != token
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_hash_token_differs_for_different_tokens() -> None:
    assert security.hash_token("token-a") != security.hash_token("token-b")


def test_constant_time_equals_matches_only_identical_strings() -> None:
    assert security.constant_time_equals("csrf-abc123", "csrf-abc123")
    assert not security.constant_time_equals("csrf-abc123", "csrf-abc124")
    # Different lengths must not raise — a naive `==` wouldn't, but this wraps
    # `hmac.compare_digest`, which is pickier about its inputs.
    assert not security.constant_time_equals("short", "a-lot-longer-string")


def test_expires_in_returns_a_tz_aware_future_moment() -> None:
    before = datetime.now(UTC)

    moment = security.expires_in(60)

    assert moment.tzinfo is not None
    assert before < moment <= before + timedelta(seconds=61)


def test_is_expired_true_for_a_past_aware_moment() -> None:
    assert security.is_expired(datetime.now(UTC) - timedelta(seconds=1))


def test_is_expired_false_for_a_future_aware_moment() -> None:
    assert not security.is_expired(datetime.now(UTC) + timedelta(minutes=5))


def test_is_expired_treats_a_naive_moment_as_utc() -> None:
    """Postgres can hand back naive datetimes for a `timestamptz` column depending
    on the driver path; this must not silently misread one as belonging to the
    server's local time zone instead of UTC."""
    naive_past = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
    naive_future = datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=5)

    assert security.is_expired(naive_past)
    assert not security.is_expired(naive_future)


def test_generate_csrf_token_is_unique_and_url_safe() -> None:
    a = security.generate_csrf_token()
    b = security.generate_csrf_token()

    assert a != b
    assert len(a) > 32
    assert all(c.isalnum() or c in "-_" for c in a)
