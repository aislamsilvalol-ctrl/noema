"""What the lesson keeps: never a credential, never mangled prose."""

from __future__ import annotations

import pytest

from noema.core.secrets import REDACTED, scrub, scrub_value

# Built by concatenation so the diff itself is not a secret-shaped literal
# that push protection (rightly) refuses.
AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
OPENAI = "sk-" + "a" * 32
STRIPE = "sk_" + "live_" + "B" * 24
JWT = "eyJ" + "a" * 20 + "." + "b" * 20 + "." + "c" * 20
PEM = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\nabc\n-----END RSA PRIVATE KEY-----"


@pytest.mark.parametrize("secret", [AWS, OPENAI, STRIPE, JWT, PEM])
def test_a_pasted_credential_is_not_kept(secret: str) -> None:
    kept, found = scrub(f"my code is: client = Client({secret!r}) why does it fail?")

    assert secret not in kept
    assert REDACTED in kept
    assert found == 1


@pytest.mark.parametrize(
    "prose",
    [
        "Explain how the sk-means algorithm differs from k-means.",
        "O que é AKIA na biologia? Não sei.",
        "A private key is a secret number used to sign messages.",
        "Tokens like eyJ are base64 for a curly brace.",
    ],
)
def test_ordinary_text_is_left_alone(prose: str) -> None:
    assert scrub(prose) == (prose, 0)


def test_memory_shapes_are_scrubbed_all_the_way_down() -> None:
    memory = {
        "mastered": ["closures"],
        "notes": [{"said": f"here is my key {OPENAI}"}],
        "turns": 3,
    }

    out = scrub_value(memory)

    assert out["notes"][0]["said"] == f"here is my key {REDACTED}"
    assert out["mastered"] == ["closures"] and out["turns"] == 3
