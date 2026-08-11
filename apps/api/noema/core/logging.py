"""Structured logging with secret redaction.

The redaction processor is not defence in depth for its own sake — BYOK means a key
in a log line is a user's money on a disk we might ship to a log aggregator. There is
a test asserting a known key never survives this pipeline.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

# Provider key shapes, plus a generic long-token catch-all.
_SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"AIza[A-Za-z0-9_\-]{20,}"),
    re.compile(r"sk-or-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
]

_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "password",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "secret",
        "master_key",
        "session_secret",
        "ciphertext",
        "wrapped_key",
    }
)

REDACTED = "[redacted]"


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        for pattern in _SECRET_PATTERNS:
            value = pattern.sub(REDACTED, value)
        return value
    if isinstance(value, dict):
        return {k: (REDACTED if k.lower() in _SENSITIVE_KEYS else _redact_value(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_redact_value(v) for v in value)
    return value


def redact_secrets(
    _logger: Any, _method: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    return {
        key: (REDACTED if key.lower() in _SENSITIVE_KEYS else _redact_value(value))
        for key, value in event_dict.items()
    }


def configure_logging(level: str = "info", json_output: bool = True) -> None:
    logging.basicConfig(
        format="%(message)s", stream=sys.stdout, level=getattr(logging, level.upper(), logging.INFO)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_secrets,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
            if json_output
            else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
