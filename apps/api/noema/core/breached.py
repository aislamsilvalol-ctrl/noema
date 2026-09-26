"""Has this password been in a public breach? (k-anonymity, Have I Been Pwned)

Only the first five characters of the password's SHA-1 leave this server;
the service answers with every suffix it knows under that prefix, and the
match happens here. The password, and even its full hash, are never sent.

Best effort by design: two seconds at most, and any failure (network, the
service down, a strange answer) lets the password through. A breach list is
a second line of defence; it must not become the reason nobody can sign up.
"""

from __future__ import annotations

import hashlib

import httpx

from noema.core.logging import get_logger

log = get_logger(__name__)

RANGE_API = "https://api.pwnedpasswords.com/range/"
TIMEOUT_SECONDS = 2.0


async def times_breached(
    password: str, *, client: httpx.AsyncClient | None = None
) -> int:
    """How often the password appears in known breaches; 0 when unknown."""
    digest = hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    owns = client is None
    client = client or httpx.AsyncClient(timeout=TIMEOUT_SECONDS)
    try:
        response = await client.get(RANGE_API + prefix, headers={"Add-Padding": "true"})
        response.raise_for_status()
    except httpx.HTTPError as exc:
        log.info("breached.unavailable", error=type(exc).__name__)
        return 0
    finally:
        if owns:
            await client.aclose()
    for line in response.text.splitlines():
        found, _, count = line.strip().partition(":")
        if found == suffix:
            try:
                return int(count)
            except ValueError:
                return 0
    return 0
