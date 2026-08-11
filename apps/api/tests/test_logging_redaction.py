"""BYOK means a leaked log line costs a user money. These tests are load-bearing."""

from __future__ import annotations

import json
import logging

import pytest
import structlog

from noema.core.logging import REDACTED, configure_logging, redact_secrets

KEYS = [
    "sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "sk-proj-BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",
    "AIzaSyCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
    "sk-or-v1-DDDDDDDDDDDDDDDDDDDDDDDDDDDD",
]


@pytest.mark.parametrize("key", KEYS)
def test_keys_are_stripped_from_free_text(key: str) -> None:
    result = redact_secrets(None, "info", {"event": f"calling provider with {key}"})
    assert key not in result["event"]
    assert REDACTED in result["event"]


@pytest.mark.parametrize(
    "field", ["api_key", "password", "authorization", "refresh_token"]
)
def test_sensitive_field_names_are_dropped_whatever_the_value(field: str) -> None:
    result = redact_secrets(None, "info", {"event": "call", field: "anything at all"})
    assert result[field] == REDACTED


def test_nested_structures_are_redacted() -> None:
    payload = {
        "event": "provider.configured",
        "config": {"provider": "anthropic", "api_key": KEYS[0], "models": ["a", "b"]},
        "history": [{"token": "secret-value"}],
    }
    result = redact_secrets(None, "info", payload)

    serialized = json.dumps(result)
    assert KEYS[0] not in serialized
    assert "secret-value" not in serialized
    assert "anthropic" in serialized  # non-sensitive context survives


def test_a_key_never_survives_the_configured_pipeline(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """End to end: the processor chain that actually runs in the app."""
    configure_logging("info", json_output=True)
    log = structlog.get_logger("test")

    with caplog.at_level(logging.INFO):
        log.info("provider.call", api_key=KEYS[0], detail=f"used {KEYS[1]}")

    captured = caplog.text
    for key in (KEYS[0], KEYS[1]):
        assert key not in captured


def test_ordinary_values_are_left_alone() -> None:
    result = redact_secrets(
        None, "info", {"event": "notebook.created", "notebook_id": "abc-123", "count": 4}
    )
    assert result["notebook_id"] == "abc-123"
    assert result["count"] == 4
