#!/usr/bin/env python3
"""Run the Freud golden path against a deployment and write the transcript down.

    NOEMA_EMAIL=… NOEMA_PASSWORD=… scripts/eval-teaching.py https://api.example.com evals/teaching/freud-after

Plays the spec's §119 sequence (the same six learner messages as the baseline
in evals/teaching/baseline/freud-before.md) through `POST /ai/professor` as one
teaching session, then reads the session back. Writes `<out>.md` (the
transcript, per-turn timings, the session state after each turn) and
`<out>.json` (the same, for diffs). Judgement is left to the reader and to the
rubric in docs/teaching-engine-audit.md §2 — this only makes the comparison
possible.

Spends six model calls. Credentials come from the environment only.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import ssl
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

try:
    import certifi

    _SSL_CONTEXT: ssl.SSLContext | None = ssl.create_default_context(
        cafile=certifi.where()
    )
except Exception:
    _SSL_CONTEXT = None

SCRIPT = [
    "Me ensine Psicologia segundo Freud.",
    "Não entendi o que é inconsciente.",
    "Então qualquer coisa que eu esqueci está no inconsciente?",
    "Agora entendi.",
    "Me testa.",
    "Acho que é o inconsciente, porque é tudo que eu não estou pensando agora.",
]


def main(base: str, out: str) -> int:
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
    with opener.open(
        urllib.request.Request(
            f"{api}/auth/login",
            data=json.dumps({"email": email, "password": password}).encode(),
            headers={"content-type": "application/json"},
            method="POST",
        ),
        timeout=30,
    ) as response:
        if response.status != 200:
            print(f"FAIL  login returned {response.status}")
            return 1
    csrf = next(c.value for c in jar if c.name == "noema_csrf")
    assert csrf is not None
    headers = {"content-type": "application/json", "x-csrf-token": csrf}

    meta = json.loads(opener.open(f"{api}/meta", timeout=30).read())

    history: list[dict[str, str]] = []
    turns: list[dict[str, Any]] = []
    session_id: str | None = None

    for learner in SCRIPT:
        history.append({"role": "user", "content": learner})
        body: dict[str, object] = {"messages": history, "grounded": False}
        if session_id:
            body["session_id"] = session_id
        request = urllib.request.Request(
            f"{api}/ai/professor",
            data=json.dumps(body).encode(),
            headers=headers,
            method="POST",
        )
        started = time.time()
        first_token: float | None = None
        text: list[str] = []
        intent = ""
        event = None
        with opener.open(request, timeout=240) as response:
            for raw in response:
                line = raw.decode().rstrip("\n")
                if line.startswith("event: "):
                    event = line[7:]
                elif line.startswith("data: "):
                    data = json.loads(line[6:])
                    if event == "session":
                        session_id = str(data["id"])
                    elif event == "intent":
                        intent = str(data["intent"])
                    elif event == "token":
                        if first_token is None:
                            first_token = time.time() - started
                        text.append(data["text"])
                    elif event == "error":
                        print(f"FAIL  stream error: {data}")
                        return 1
        reply = "".join(text)
        history.append({"role": "assistant", "content": reply})

        state = json.loads(
            opener.open(
                urllib.request.Request(
                    f"{api}/ai/sessions/{session_id}", headers=headers
                ),
                timeout=30,
            ).read()
        )
        turns.append(
            {
                "learner": learner,
                "intent": intent,
                "reply": reply,
                "first_token_s": round(first_token or 0, 1),
                "total_s": round(time.time() - started, 1),
                "words": len(reply.split()),
                "state": {
                    k: state.get(k)
                    for k in (
                        "subject",
                        "current_topic",
                        "current_concept",
                        "plan",
                        "turn_count",
                    )
                },
            }
        )
        print(
            f"ok    turn {len(turns)}: {intent or '?'} in {turns[-1]['total_s']}s,"
            f" {turns[-1]['words']} words, concept={state.get('current_concept')!r}"
        )

    revision = meta.get("revision", "unknown")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(f"{out}.json").write_text(
        json.dumps(
            {"revision": revision, "session_id": session_id, "turns": turns}, indent=2
        )
    )
    lines = [
        f"# Freud golden path — revision {revision}",
        "",
        f"Session `{session_id}` against {base}. Same six learner messages as the baseline.",
        "",
        "| turn | intent | first token | total | words | concept after |",
        "|---|---|---|---|---|---|",
    ]
    for i, t in enumerate(turns, start=1):
        lines.append(
            f"| {i} | {t['intent']} | {t['first_token_s']} s | {t['total_s']} s | {t['words']} |"
            f" {t['state']['current_concept'] or '—'} |"
        )
    for i, t in enumerate(turns, start=1):
        lines += [
            "",
            f"## Turn {i}",
            "",
            f"**Learner:** {t['learner']}",
            "",
            f"*session after: {json.dumps(t['state'], ensure_ascii=False)}*",
            "",
            "**NOEMA:**",
            "",
            str(t["reply"]),
        ]
    Path(f"{out}.md").write_text("\n".join(lines) + "\n")
    print(f"PASS  wrote {out}.md and {out}.json")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
