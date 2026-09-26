"""The breach check sends five hex characters and fails open."""

from __future__ import annotations

import hashlib

import httpx
import pytest

from noema.core.breached import times_breached

pytestmark = pytest.mark.asyncio

PASSWORD = "correct-horse-battery-staple"
DIGEST = hashlib.sha1(PASSWORD.encode()).hexdigest().upper()


async def test_only_the_prefix_leaves_and_the_match_happens_here() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        body = f"0000000000000000000000000000000000A:1\n{DIGEST[5:]}:3303003\n"
        return httpx.Response(200, text=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await times_breached(PASSWORD, client=client) == 3303003

    assert seen == [f"https://api.pwnedpasswords.com/range/{DIGEST[:5]}"]
    assert PASSWORD not in seen[0] and DIGEST not in seen[0]


async def test_an_unknown_password_is_zero() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text="ABC:1\n"))
    async with httpx.AsyncClient(transport=transport) as client:
        assert await times_breached("a-long-unusual-phrase-of-mine", client=client) == 0


async def test_the_service_down_lets_the_password_through() -> None:
    def boom(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow")

    async with httpx.AsyncClient(transport=httpx.MockTransport(boom)) as client:
        assert await times_breached(PASSWORD, client=client) == 0
