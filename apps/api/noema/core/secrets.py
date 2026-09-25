"""Credential-shaped strings, and how to take them out of text.

One list, used twice: the log processor redacts these from every log line,
and the lesson redacts them from what it keeps. A learner who pastes code
with a live API key in it, or a private key, gets taught; the transcript and
the memory built from it keep `[redacted]` instead. NOEMA is not a place to
store secrets by accident.

High precision on purpose: every pattern is a shape real credentials have
and prose does not, so ordinary text is never mangled.
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "[redacted]"

SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"AIza[A-Za-z0-9_\-]{20,}"),
    re.compile(r"sk-or-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bpk_(?:live|test)_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\brk_(?:live|test)_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bwhsec_[A-Za-z0-9]{16,}\b"),
    # A JSON Web Token: three base64url parts, the first always a JSON object.
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    # A PEM private key, the whole block.
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        re.DOTALL,
    ),
)


def scrub(text: str) -> tuple[str, int]:
    """The text with every credential replaced, and how many there were."""
    found = 0
    for pattern in SECRET_PATTERNS:
        text, count = pattern.subn(REDACTED, text)
        found += count
    return text, found


def scrub_value(value: Any) -> Any:
    """`scrub` through any JSON-shaped value: strings, lists, dicts."""
    if isinstance(value, str):
        return scrub(value)[0]
    if isinstance(value, list):
        return [scrub_value(item) for item in value]
    if isinstance(value, dict):
        return {key: scrub_value(item) for key, item in value.items()}
    return value
