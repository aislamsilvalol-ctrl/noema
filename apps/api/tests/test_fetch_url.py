"""SSRF checks for link ingestion.

The resolver and the transport are fakes. What is under test is the policy:
https only, blocked addresses never get a connection, every redirect is
resolved again, and a body past the cap stops the read.
"""

from __future__ import annotations

import ipaddress
from collections.abc import AsyncIterator

import httpcore
import pytest

from noema.ingestion.fetch_url import (
    UrlRejected,
    UrlTooLarge,
    _Hop,
    _PinnedBackend,
    _Response,
    fetch_https,
    is_blocked_ip,
    looks_like_html,
)

PUBLIC = "1.1.1.1"
OTHER = "8.8.8.8"


class _Body:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self.pulled = 0
        self.closed = False

    def __aiter__(self) -> AsyncIterator[bytes]:
        return self._iter()

    async def _iter(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            self.pulled += 1
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


class _Script:
    def __init__(self, responses: list[tuple[int, dict[str, str], list[bytes]]]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []
        self.bodies: list[_Body] = []

    async def __call__(self, hop: _Hop) -> _Response:
        self.calls.append((str(hop.url), hop.ip))
        status, headers, chunks = self._responses.pop(0)
        body = _Body(chunks)
        self.bodies.append(body)
        return _Response(status_code=status, headers=headers, body=body)


def _ok(body: bytes = b"<!doctype html><html><body>hi</body></html>") -> _Script:
    return _Script([(200, {"content-type": "text/html"}, [body])])


def test_blocked_addresses_cover_loopback_private_link_local_and_metadata() -> None:
    blocked = [
        "127.0.0.1",
        "10.1.1.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "100.100.100.200",
        "0.0.0.0",
        "::1",
        "fe80::1",
        "fd00:ec2::254",
        "::ffff:127.0.0.1",
        "::ffff:169.254.169.254",
    ]
    allowed = ["8.8.8.8", "1.1.1.1", "2001:4860:4860::8888", "::ffff:8.8.8.8"]
    for raw in blocked:
        assert is_blocked_ip(ipaddress.ip_address(raw)), raw
    for raw in allowed:
        assert not is_blocked_ip(ipaddress.ip_address(raw)), raw


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/notes",
        "HTTP://example.com/notes",
        "ftp://example.com/notes",
        "https://user:secret@example.com/notes",
        "https://127.0.0.1/latest",
        "https://127.0.0.1.nip.io/latest",  # name is public-looking; resolver decides
        "https://[::1]/latest",
        "https://169.254.169.254/latest/meta-data/",
        "https://2130706433/",  # decimal form of 127.0.0.1
        "https://10.1.1.1/",
        "https://metadata.google.internal/computeMetadata/v1/",
        "https://printer.local/status",
        "https://db.internal/admin",
    ],
)
async def test_blocked_hosts_and_non_https_never_dial(url: str) -> None:
    # The nip.io name is only blocked once the resolver reports a private address.
    def resolve(host: str, port: int) -> list[str]:
        if host == "127.0.0.1.nip.io":
            return ["127.0.0.1"]
        raise AssertionError(f"resolved {host}")

    script = _ok()

    with pytest.raises(UrlRejected):
        await fetch_https(url, max_bytes=1024, resolve=resolve, exchange=script)

    assert script.calls == []


async def test_http_redirect_is_refused_before_the_next_hop_is_resolved() -> None:
    def resolve(host: str, port: int) -> list[str]:
        if host == "ok.example":
            return [PUBLIC]
        raise AssertionError(f"resolved {host}")

    script = _Script([(302, {"location": "http://ok.example/secret"}, [b""])])

    with pytest.raises(UrlRejected, match="https"):
        await fetch_https(
            "https://ok.example/start",
            max_bytes=1024,
            resolve=resolve,
            exchange=script,
        )

    assert script.calls == [("https://ok.example/start", PUBLIC)]


async def test_redirect_to_a_metadata_address_is_checked_again_and_not_dialed() -> None:
    def resolve(host: str, port: int) -> list[str]:
        if host == "ok.example":
            return [PUBLIC]
        if host == "meta.example":
            return ["169.254.169.254"]
        raise AssertionError(host)

    script = _Script(
        [(302, {"location": "https://meta.example/latest/meta-data/"}, [b""])]
    )

    with pytest.raises(UrlRejected, match="not allowed"):
        await fetch_https(
            "https://ok.example/go",
            max_bytes=1024,
            resolve=resolve,
            exchange=script,
        )

    assert script.calls == [("https://ok.example/go", PUBLIC)]


async def test_a_public_redirect_is_followed_on_the_rechecked_address() -> None:
    def resolve(host: str, port: int) -> list[str]:
        return {"ok.example": [PUBLIC], "cdn.example": [OTHER]}[host]

    body = b"<!doctype html><html><body>chapter</body></html>"
    script = _Script(
        [
            (302, {"location": "https://cdn.example/chapter.html"}, [b""]),
            (
                200,
                {
                    "content-type": "text/html",
                    "content-disposition": 'attachment; filename="chapter.html"',
                },
                [body],
            ),
        ]
    )

    fetched = await fetch_https(
        "https://ok.example/start",
        max_bytes=1024,
        resolve=resolve,
        exchange=script,
    )

    assert script.calls == [
        ("https://ok.example/start", PUBLIC),
        ("https://cdn.example/chapter.html", OTHER),
    ]
    assert fetched.url == "https://cdn.example/chapter.html"
    assert fetched.data == body
    assert fetched.filename == "chapter.html"
    assert all(item.closed for item in script.bodies)


async def test_a_resolver_that_returns_any_private_address_is_refused() -> None:
    def resolve(host: str, port: int) -> list[str]:
        return [PUBLIC, "10.0.0.5"]

    script = _ok()
    with pytest.raises(UrlRejected, match="not allowed"):
        await fetch_https(
            "https://split.example/a", max_bytes=1024, resolve=resolve, exchange=script
        )
    assert script.calls == []


async def test_response_over_the_size_cap_stops_reading() -> None:
    script = _Script([(200, {}, [b"a" * 100, b"b" * 100, b"c" * 100])])

    with pytest.raises(UrlTooLarge):
        await fetch_https(
            "https://ok.example/big",
            max_bytes=150,
            resolve=lambda host, port: [PUBLIC],
            exchange=script,
        )

    assert script.bodies[0].pulled == 2
    assert script.bodies[0].closed


async def test_content_length_over_the_cap_does_not_read_the_body() -> None:
    script = _Script([(200, {"content-length": "999999"}, [b"x" * 50])])

    with pytest.raises(UrlTooLarge):
        await fetch_https(
            "https://ok.example/big",
            max_bytes=100,
            resolve=lambda host, port: [PUBLIC],
            exchange=script,
        )

    assert script.bodies[0].pulled == 0
    assert script.bodies[0].closed


async def test_redirect_limit_does_not_fetch_past_the_cap() -> None:
    def resolve(host: str, port: int) -> list[str]:
        return [PUBLIC]

    script = _Script(
        [
            (302, {"location": "https://ok.example/1"}, [b""]),
            (302, {"location": "https://ok.example/2"}, [b""]),
        ]
    )

    with pytest.raises(UrlRejected, match="redirected too many"):
        await fetch_https(
            "https://ok.example/0",
            max_bytes=100,
            max_redirects=1,
            resolve=resolve,
            exchange=script,
        )

    assert [url for url, _ip in script.calls] == [
        "https://ok.example/0",
        "https://ok.example/1",
    ]


def test_looks_like_html_follows_the_content_type_and_the_bytes() -> None:
    assert looks_like_html(b"<html><body>x</body></html>", None)
    assert looks_like_html(b"not really", "text/html; charset=utf-8")
    assert not looks_like_html(b"# a note\n", "text/plain")
    assert not looks_like_html(b"%PDF-1.7", "application/pdf")


async def test_pinned_backend_dials_the_checked_address_not_the_name() -> None:
    class _Recording(httpcore.AsyncNetworkBackend):
        def __init__(self) -> None:
            self.hosts: list[str] = []

        async def connect_tcp(
            self,
            host: str,
            port: int,
            timeout: float | None = None,  # noqa: ASYNC109 — httpcore's parameter name
            local_address: str | None = None,
            socket_options: object = None,
        ) -> httpcore.AsyncNetworkStream:
            self.hosts.append(host)
            raise RuntimeError("stop")

        async def connect_unix_socket(
            self,
            path: str,
            timeout: float | None = None,  # noqa: ASYNC109 — httpcore's parameter name
            socket_options: object = None,
        ) -> httpcore.AsyncNetworkStream:
            raise AssertionError(path)

        async def sleep(self, seconds: float) -> None:
            return None

    inner = _Recording()
    backend = _PinnedBackend(PUBLIC, inner=inner)

    with pytest.raises(RuntimeError, match="stop"):
        await backend.connect_tcp("example.com", 443)

    assert inner.hosts == [PUBLIC]
