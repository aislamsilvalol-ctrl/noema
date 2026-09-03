#!/usr/bin/env python3
"""Does a deployed Professor remember a lesson? Ask it, twice, then read back.

    NOEMA_EMAIL=… NOEMA_PASSWORD=… scripts/check-teaching-session.py https://api.example.com

Opens a lesson with one message, continues it with a second message carrying
the session id, then fetches the session and checks that both learner turns
and both Noema replies were written and that "latest" points at it. This is
the "I come back tomorrow" contract, exercised against a real deployment — the
CI test covers the code path; this covers the deployed database, the proxy,
and the transaction behaviour under a real stream, which is where it broke
the first time.

Spends two short model calls. Credentials come from the environment only.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import ssl
import sys
import time
import urllib.request

try:
    import certifi

    _SSL_CONTEXT: ssl.SSLContext | None = ssl.create_default_context(cafile=certifi.where())
except Exception:  # noqa: BLE001 - certifi is optional; fall back to system trust
    _SSL_CONTEXT = None


def main(base: str) -> int:
    email, password = os.environ.get("NOEMA_EMAIL"), os.environ.get("NOEMA_PASSWORD")
    if not email or not password:
        print("set NOEMA_EMAIL and NOEMA_PASSWORD", file=sys.stderr)
        return 2
    api = f"{base.rstrip('/')}/api/v1"

    jar = http.cookiejar.CookieJar()
    handlers: list[urllib.request.BaseHandler] = [urllib.request.HTTPCookieProcessor(jar)]
    if _SSL_CONTEXT is not None:
        handlers.append(urllib.request.HTTPSHandler(context=_SSL_CONTEXT))
    opener = urllib.request.build_opener(*handlers)
    login = urllib.request.Request(
        f"{api}/auth/login",
        data=json.dumps({"email": email, "password": password}).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with opener.open(login, timeout=30) as response:
        if response.status != 200:
            print(f"FAIL  login returned {response.status}")
            return 1
    csrf = next(c.value for c in jar if c.name == "noema_csrf")

    def turn(body: dict[str, object]) -> tuple[dict[str, object], str, float]:
        request = urllib.request.Request(
            f"{api}/ai/professor",
            data=json.dumps(body).encode(),
            headers={"content-type": "application/json", "x-csrf-token": csrf},
            method="POST",
        )
        started, session, text, event = time.time(), {}, [], None
        with opener.open(request, timeout=180) as response:
            for raw in response:
                line = raw.decode().rstrip("\n")
                if line.startswith("event: "):
                    event = line[7:]
                elif line.startswith("data: "):
                    data = json.loads(line[6:])
                    if event == "session":
                        session = data
                    elif event == "token":
                        text.append(data["text"])
                    elif event == "error":
                        print(f"FAIL  stream error: {data}")
                        raise SystemExit(1)
        return session, "".join(text), time.time() - started

    first = "Explique o que é o inconsciente para Freud, em duas frases."
    opened, reply, seconds = turn({"messages": [{"role": "user", "content": first}], "grounded": False})
    if not opened.get("created") or not opened.get("id"):
        print(f"FAIL  first message did not open a session: {opened}")
        return 1
    session_id = str(opened["id"])
    print(f"ok    opened {session_id[:8]}… in {seconds:.1f}s ({len(reply.split())} words)")

    second = "E o pré-consciente? Uma frase."
    resumed, reply2, seconds2 = turn(
        {
            "session_id": session_id,
            "messages": [
                {"role": "user", "content": first},
                {"role": "assistant", "content": reply},
                {"role": "user", "content": second},
            ],
            "grounded": False,
        }
    )
    if resumed.get("created") is not False or str(resumed.get("id")) != session_id:
        print(f"FAIL  second message did not resume the session: {resumed}")
        return 1
    print(f"ok    resumed in {seconds2:.1f}s ({len(reply2.split())} words)")

    with opener.open(
        urllib.request.Request(f"{api}/ai/sessions/{session_id}", headers={"x-csrf-token": csrf}),
        timeout=30,
    ) as response:
        stored = json.loads(response.read())
    roles = [t["role"] for t in stored["turns"]]
    if roles != ["learner", "noema", "learner", "noema"]:
        print(f"FAIL  stored turns are {roles}, expected learner/noema/learner/noema")
        return 1
    if stored["turn_count"] != 4:
        print(f"FAIL  turn_count is {stored['turn_count']}, expected 4")
        return 1
    print("ok    both turns of both messages are stored, in order")

    with opener.open(
        urllib.request.Request(f"{api}/ai/sessions/latest", headers={"x-csrf-token": csrf}),
        timeout=30,
    ) as response:
        latest = json.loads(response.read())
    if not latest or str(latest["id"]) != session_id:
        print("FAIL  /ai/sessions/latest does not point at this lesson")
        return 1
    print("ok    latest open lesson is this one")
    print("PASS  the Professor remembers the lesson")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
