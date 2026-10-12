"""SSRF-safe HTTPS fetch for link ingestion.

Each hop is resolved and checked before a connection is opened, and the
connection goes to that checked address. A later DNS answer cannot point the
same name at a loopback, private, link-local, or metadata address.

``academic.ocw.http_fetch`` is not used here. It follows redirects in one
client call, so a hop is never re-checked.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
import ssl
from collections.abc import (
    AsyncIterable,
    AsyncIterator,
    Awaitable,
    Callable,
    Iterable,
    Mapping,
)
from dataclasses import dataclass
from urllib.parse import unquote

import httpcore
import httpx

from noema.core.errors import NoemaError
from noema.core.logging import get_logger

log = get_logger(__name__)

__all__ = [
    "FetchedUrl",
    "UrlRejected",
    "UrlTooLarge",
    "fetch_https",
    "is_blocked_ip",
    "looks_like_html",
]

#: Five redirects, then stop. Each one is a new resolution.
MAX_REDIRECTS = 5
DEFAULT_TIMEOUT_SECONDS = 20.0
_MAX_URL_LENGTH = 2048

_REDIRECTS = frozenset({301, 302, 303, 307, 308})

#: Names that are internal even when a resolver answers with a public address.
_BLOCKED_NAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata",
        "metadata.google.internal",
        "metadata.goog",
    }
)
_BLOCKED_SUFFIXES = (".local", ".localhost", ".internal", ".localdomain")

_FILENAME_STAR = re.compile(r"filename\*\s*=\s*(?:UTF-8|utf-8)?''([^;]+)", re.IGNORECASE)
_FILENAME = re.compile(r"""filename\s*=\s*(?:"([^"]+)"|([^";]+))""", re.IGNORECASE)

_USER_AGENT = b"noema-ingest/1.0 (+https://github.com/aislamsilvalol-ctrl/noema)"


class UrlRejected(NoemaError):
    slug = "url-rejected"
    title = "URL rejected"
    status_code = 400


class UrlTooLarge(NoemaError):
    slug = "url-too-large"
    title = "Page too large"
    status_code = 413


@dataclass(frozen=True, slots=True)
class FetchedUrl:
    """Bytes of one page, after redirects, ready for the upload checks."""

    url: str
    data: bytes
    filename: str | None
    content_type: str | None


@dataclass(frozen=True, slots=True)
class _Hop:
    url: httpx.URL
    ip: str
    port: int


@dataclass(slots=True)
class _Response:
    status_code: int
    headers: dict[str, str]
    body: AsyncIterable[bytes]


Resolver = Callable[[str, int], list[str]]
Exchange = Callable[[_Hop], Awaitable[_Response]]


def is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True for loopback, private, link-local, metadata, and non-global space.

    IPv4-mapped IPv6 is judged as the IPv4 address it contains, so
    ``::ffff:127.0.0.1`` is blocked and ``::ffff:8.8.8.8`` is not.
    """
    if isinstance(ip, ipaddress.IPv6Address):
        mapped = ip.ipv4_mapped
        if mapped is not None:
            return is_blocked_ip(mapped)
    if (
        ip.is_multicast
        or ip.is_unspecified
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_private
    ):
        return True
    return not ip.is_global


def looks_like_html(data: bytes, content_type: str | None) -> bool:
    """Whether fetched bytes should be parsed as a page rather than as a file."""
    if content_type:
        media = content_type.split(";", 1)[0].strip().lower()
        if media in {"text/html", "application/xhtml+xml"}:
            return True
    head = data.lstrip()[:256].lower()
    return head.startswith((b"<!doctype html", b"<html", b"<head", b"<body"))


async def fetch_https(
    url: str,
    *,
    max_bytes: int,
    max_redirects: int = MAX_REDIRECTS,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    resolve: Resolver | None = None,
    exchange: Exchange | None = None,
) -> FetchedUrl:
    """GET ``url``, following redirects only after each hop is checked again.

    ``resolve`` and ``exchange`` exist so tests can supply a resolver and a
    transport. The defaults resolve with the system resolver and connect to
    the address that check accepted.
    """
    if max_bytes < 1:
        raise UrlTooLarge("That page is larger than the upload limit.")

    resolver = resolve or resolve_host
    transport = exchange or (
        lambda hop: _pinned_exchange(hop, timeout_seconds=timeout_seconds)
    )
    current = _parse_https(url)
    seen: set[str] = set()
    hops = max(0, max_redirects)

    for hop in range(hops + 1):
        key = str(current)
        if key in seen:
            raise UrlRejected("That URL redirected to itself.")
        seen.add(key)

        request = await _checked_hop(current, resolver)
        response = await transport(request)
        try:
            if response.status_code in _REDIRECTS:
                if hop == hops:
                    raise UrlRejected("That URL redirected too many times.")
                current = _next_url(current, response.headers.get("location"))
                continue

            if not 200 <= response.status_code < 300:
                raise UrlRejected(f"The page returned HTTP {response.status_code}.")

            length = _content_length(response.headers)
            if length is not None and length > max_bytes:
                raise UrlTooLarge("That page is larger than the upload limit.")

            data = await read_limited(response.body, max_bytes)
        finally:
            await _aclose(response.body)

        log.info(
            "ingest.url.fetched",
            host=current.host,
            bytes=len(data),
            status=response.status_code,
        )
        return FetchedUrl(
            url=str(current),
            data=data,
            filename=_filename(current, response.headers),
            content_type=response.headers.get("content-type"),
        )

    raise UrlRejected("That URL redirected too many times.")


def resolve_host(host: str, port: int) -> list[str]:
    """System DNS. Callers check every returned address before connecting."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UrlRejected("Could not resolve that host.") from exc
    return [str(info[4][0]) for info in infos]


async def read_limited(body: AsyncIterable[bytes], max_bytes: int) -> bytes:
    """Read ``body`` until ``max_bytes``. The next chunk past the cap stops it."""
    buf = bytearray()
    async for chunk in body:
        if not chunk:
            continue
        if len(buf) + len(chunk) > max_bytes:
            raise UrlTooLarge("That page is larger than the upload limit.")
        buf.extend(chunk)
    return bytes(buf)


def _parse_https(url: str) -> httpx.URL:
    if len(url) > _MAX_URL_LENGTH:
        raise UrlRejected("That URL is not allowed.")
    try:
        parsed = httpx.URL(url.strip())
    except httpx.InvalidURL as exc:
        raise UrlRejected("That URL is not allowed.") from exc
    if parsed.scheme != "https":
        raise UrlRejected("Only https URLs can be ingested.")
    if parsed.username or parsed.password or not parsed.host:
        raise UrlRejected("That URL is not allowed.")
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise UrlRejected("That URL is not allowed.")
    return parsed.copy_with(fragment=None)


async def _checked_hop(url: httpx.URL, resolve: Resolver) -> _Hop:
    host = url.host
    port = url.port or 443
    if not host:
        raise UrlRejected("That URL is not allowed.")
    literal = _literal_ip(host)
    if literal is not None:
        if is_blocked_ip(literal):
            log.info("ingest.url.blocked", host=host)
            raise UrlRejected("That URL is not allowed.")
        ips = [str(literal)]
    else:
        if _blocked_name(host):
            log.info("ingest.url.blocked", host=host)
            raise UrlRejected("That URL is not allowed.")
        ips = await asyncio.to_thread(resolve, host, port)
        checked: list[str] = []
        for raw in ips:
            parsed = _literal_ip(raw.split("%", 1)[0])
            if parsed is None or is_blocked_ip(parsed):
                log.info("ingest.url.blocked", host=host)
                raise UrlRejected("That URL is not allowed.")
            canonical = str(parsed)
            if canonical not in checked:
                checked.append(canonical)
        if not checked:
            raise UrlRejected("Could not resolve that host.")
        ips = checked
    return _Hop(url=url, ip=ips[0], port=port)


def _next_url(current: httpx.URL, location: str | None) -> httpx.URL:
    if not location or not location.strip():
        raise UrlRejected("That URL redirected without a destination.")
    if len(location) > _MAX_URL_LENGTH:
        raise UrlRejected("That URL is not allowed.")
    try:
        nxt = current.join(location.strip())
    except httpx.InvalidURL as exc:
        raise UrlRejected("That URL is not allowed.") from exc
    return _parse_https(str(nxt))


def _literal_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    bare = host.split("%", 1)[0]
    try:
        return ipaddress.ip_address(bare)
    except ValueError:
        pass
    # A decimal integer is an IPv4 address some stacks dial directly
    # (2130706433 is 127.0.0.1). Treat it as that address.
    if bare.isdigit():
        value = int(bare)
        if 0 <= value <= 0xFFFFFFFF:
            return ipaddress.IPv4Address(value)
    return None


def _blocked_name(host: str) -> bool:
    name = host.lower().rstrip(".")
    if name in _BLOCKED_NAMES:
        return True
    return any(name.endswith(suffix) for suffix in _BLOCKED_SUFFIXES)


def _content_length(headers: Mapping[str, str]) -> int | None:
    raw = headers.get("content-length")
    if raw is None:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value >= 0 else None


def _filename(url: httpx.URL, headers: Mapping[str, str]) -> str | None:
    disposition = headers.get("content-disposition", "")
    starred = _FILENAME_STAR.search(disposition)
    if starred:
        name = _safe_filename(starred.group(1))
        if name:
            return name
    plain = _FILENAME.search(disposition)
    if plain:
        name = _safe_filename(plain.group(1) or plain.group(2) or "")
        if name:
            return name
    segment = url.path.rsplit("/", 1)[-1]
    return _safe_filename(segment)


def _safe_filename(name: str) -> str | None:
    cleaned = unquote(name).strip().strip('"').replace("\\", "/")
    cleaned = cleaned.rsplit("/", 1)[-1].strip()
    if not cleaned or cleaned in {".", ".."}:
        return None
    return cleaned[:500]


async def _aclose(body: AsyncIterable[bytes]) -> None:
    close = getattr(body, "aclose", None)
    if close is None:
        return
    await close()


class _PinnedBackend(httpcore.AsyncNetworkBackend):
    """Dial ``ip`` whatever host the URL names, so DNS cannot move the target."""

    def __init__(
        self, ip: str, *, inner: httpcore.AsyncNetworkBackend | None = None
    ) -> None:
        self._ip = ip
        self._inner = inner if inner is not None else httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 — httpcore's parameter name
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        return await self._inner.connect_tcp(
            self._ip,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109 — httpcore's parameter name
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise UrlRejected("That URL is not allowed.")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class _ResponseBody:
    def __init__(
        self, response: httpcore.Response, pool: httpcore.AsyncConnectionPool
    ) -> None:
        self._response = response
        self._pool = pool
        self._closed = False

    def __aiter__(self) -> AsyncIterator[bytes]:
        return self._iter()

    async def _iter(self) -> AsyncIterator[bytes]:
        async for chunk in self._response.aiter_stream():
            yield chunk

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._response.aclose()
        finally:
            await self._pool.aclose()


async def _pinned_exchange(hop: _Hop, *, timeout_seconds: float) -> _Response:
    pool = httpcore.AsyncConnectionPool(
        ssl_context=httpcore.default_ssl_context(),
        max_connections=1,
        max_keepalive_connections=0,
        retries=0,
        network_backend=_PinnedBackend(hop.ip),
    )
    core_url = httpcore.URL(
        scheme=hop.url.raw_scheme,
        host=hop.url.raw_host,
        port=hop.port,
        target=hop.url.raw_path,
    )
    request = httpcore.Request(
        "GET",
        core_url,
        headers=[
            (b"user-agent", _USER_AGENT),
            (b"accept", b"text/html,application/xhtml+xml,application/pdf,*/*;q=0.8"),
        ],
        extensions={
            "timeout": {
                "connect": timeout_seconds,
                "read": timeout_seconds,
                "write": timeout_seconds,
                "pool": timeout_seconds,
            }
        },
    )
    try:
        response = await pool.handle_async_request(request)
    except (
        httpcore.TimeoutException,
        httpcore.NetworkError,
        httpcore.ProtocolError,
        ssl.SSLError,
        OSError,
    ) as exc:
        await pool.aclose()
        log.info(
            "ingest.url.fetch_failed",
            host=hop.url.host,
            error=type(exc).__name__,
        )
        raise UrlRejected("Could not fetch that page.") from exc
    except BaseException:
        await pool.aclose()
        raise
    return _Response(
        status_code=response.status,
        headers=_header_map(response.headers),
        body=_ResponseBody(response, pool),
    )


def _header_map(headers: Iterable[tuple[bytes, bytes]]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for key, value in headers:
        mapped[key.decode("latin-1").lower()] = value.decode("latin-1")
    return mapped
