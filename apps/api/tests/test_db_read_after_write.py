"""A row is committed before its 201 leaves the server (issue #22).

The compose smoke test twice read an empty list a few milliseconds after a
successful POST. The cause was not the smoke script: since FastAPI 0.118 a
dependency with ``yield`` runs its exit code -- here, ``session.commit()`` --
*after* the response body has been sent, unless the route asks for
``scope="function"``. Over a socket that is a real window: the client has its
201, sends the next request, and the row is not there yet.

The pytest suite could never see it. An in-process client collects the whole
response before handing it back, and the app's ``BaseHTTPMiddleware`` layers
run the route in a task of their own, so whether the commit or the body
comes first is an event-loop scheduling race -- which is also why the smoke
failed only now and then. This test therefore mounts the routers on a bare
FastAPI app, drives it as an ASGI application, and at the exact moment the
response body is handed to the server looks for the new row on a separate
connection. Without ``scope="function"`` that order is deterministic and
wrong; with it, deterministic and right.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import MutableMapping
from http.cookies import SimpleCookie
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from noema.api.v1 import auth, deps, library
from noema.core.config import get_settings

Scope = MutableMapping[str, Any]

PREFIX = "/api/v1"


async def _call(
    app: Any,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    cookies: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    on_body: Any = None,
) -> tuple[int, dict[str, str], bytes]:
    """One HTTP request straight through the ASGI interface.

    ``on_body`` is awaited when the first body chunk reaches ``send`` -- i.e.
    when a real server would already be writing it to the socket.
    """
    raw = json.dumps(body).encode() if body is not None else b""
    header_list: list[tuple[bytes, bytes]] = [
        (b"host", b"testserver"),
        (b"content-type", b"application/json"),
        (b"content-length", str(len(raw)).encode()),
    ]
    for name, value in (headers or {}).items():
        header_list.append((name.lower().encode(), value.encode()))
    if cookies:
        cookie = "; ".join(f"{k}={v}" for k, v in cookies.items())
        header_list.append((b"cookie", cookie.encode()))

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": header_list,
        "client": ("10.0.0.1", 1234),
        "server": ("testserver", 80),
    }
    sent = False

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": raw, "more_body": False}

    status = 0
    response_headers: dict[str, str] = {}
    set_cookies: list[str] = []
    chunks: list[bytes] = []

    async def send(message: dict[str, Any]) -> None:
        nonlocal status
        if message["type"] == "http.response.start":
            status = message["status"]
            for k, v in message.get("headers", []):
                name = k.decode().lower()
                if name == "set-cookie":
                    set_cookies.append(v.decode())
                else:
                    response_headers[name] = v.decode()
        elif message["type"] == "http.response.body":
            chunk = message.get("body", b"")
            if chunk and not chunks and on_body is not None:
                await on_body(chunk)
            chunks.append(chunk)

    await app(scope, receive, send)
    jar = SimpleCookie()
    for raw_cookie in set_cookies:
        jar.load(raw_cookie)
    response_headers["_cookies"] = json.dumps({k: m.value for k, m in jar.items()})
    return status, response_headers, b"".join(chunks)


@pytest.fixture
async def committed_engine(db: AsyncSession) -> Any:
    """An engine of its own, for the probe and the cleanup. Requesting ``db``
    only borrows its skip-when-no-database behaviour; nothing here runs inside
    that rolled-back transaction, because the whole point is a real commit."""
    engine = create_async_engine(get_settings().database_url)
    try:
        yield engine
    finally:
        await engine.dispose()


def _bare_app() -> FastAPI:
    """The real routers and dependencies, none of the middleware (see above)."""
    app = FastAPI()
    v1 = APIRouter(prefix="/api/v1")
    v1.include_router(auth.router)
    v1.include_router(library.router)
    app.include_router(v1)
    return app


async def test_a_post_is_committed_before_its_response_body_is_sent(
    committed_engine: Any,
) -> None:
    app = _bare_app()
    email = f"raw-{uuid.uuid4().hex[:10]}@example.com"

    status, headers, _ = await _call(
        app,
        "POST",
        f"{PREFIX}/auth/register",
        body={"email": email, "password": "correct-horse-battery", "display_name": "Raw"},
    )
    assert status == 201, headers
    cookies = json.loads(headers["_cookies"])
    assert deps.SESSION_COOKIE in cookies and deps.CSRF_COOKIE in cookies
    csrf = {deps.CSRF_HEADER: cookies[deps.CSRF_COOKIE]}

    try:
        status, _, body = await _call(
            app, "GET", f"{PREFIX}/workspaces", cookies=cookies, headers=csrf
        )
        assert status == 200, body
        workspace_id = json.loads(body)["items"][0]["id"]

        seen_at_send: dict[str, Any] = {}

        async def probe(chunk: bytes) -> None:
            subject_id = json.loads(chunk)["id"]
            # A different connection, outside any transaction of the request:
            # exactly what the next request from the client will be.
            async with committed_engine.connect() as conn:
                count = await conn.scalar(
                    text("SELECT count(*) FROM subjects WHERE id = :id"),
                    {"id": subject_id},
                )
            seen_at_send["id"] = subject_id
            seen_at_send["visible"] = count == 1

        status, _, body = await _call(
            app,
            "POST",
            f"{PREFIX}/subjects",
            body={"workspace_id": workspace_id, "title": "Read after write"},
            cookies=cookies,
            headers=csrf,
            on_body=probe,
        )
        assert status == 201, body
        assert seen_at_send.get("visible") is True, (
            "the subject row was not visible to another connection when the "
            "201 body was being sent -- the session committed after the response"
        )
    finally:
        async with committed_engine.begin() as conn:
            await conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})
