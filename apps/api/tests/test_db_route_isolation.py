"""Cross-user isolation at the HTTP layer, over every route that takes an id.

`test_db_tenancy.py` proves the repository scopes by owner. This proves the
routes use it: Bob, signed in and holding a valid CSRF token, presents each of
Alice's ids to every route that accepts one — in the path, in a query string,
in a JSON body — and must get a 403/404 (or, for a filtered list, nothing of
Alice's), and Alice's rows must all still be there afterwards.

The route list is read from the app itself, so a route added later is swept
without anyone remembering to add it here. A route that cannot be judged must
be named in ``NOT_JUDGED`` with the reason.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.api.v1 import deps
from noema.core.config import Settings
from noema.db import models as m
from noema.db.base import get_session, utcnow
from noema.main import app
from noema.services.auth import AuthService

MARKER = "ALICE-PRIVATE"

#: Probes the sweep cannot judge by status alone, with why. Each was read.
NOT_JUDGED: dict[str, str] = {
    # `ChatIn` is shared with the Professor; /ai/chat never reads session_id
    # (it keeps no lesson), so its 200 names nothing of Alice's.
    "POST /api/v1/ai/chat [session_id]": "session_id is ignored by /ai/chat",
}

#: Every id name the sweep knows a value for.
ID_NAMES = [
    "workspace_id",
    "subject_id",
    "notebook_id",
    "note_id",
    "source_id",
    "concept_id",
    "edge_id",
    "card_id",
    "question_id",
    "exam_id",
    "mistake_id",
    "goal_id",
    "credential_id",
    "journey_id",
    "summary_id",
    "assessment_id",
    "token_id",
    "target_user_id",
    "session_id",
    "src_id",
    "dst_id",
    "answer_id",
]


async def build_alice(db: AsyncSession, alice: m.User) -> dict[str, Any]:
    """One of everything an id route can name, each carrying the marker."""
    o = alice.id

    def add(row: Any) -> Any:
        db.add(row)
        return row

    ws = add(m.Workspace(owner_id=o, title=MARKER, slug=f"ws-{uuid.uuid4().hex[:8]}"))
    await db.flush()
    subject = add(m.Subject(owner_id=o, workspace_id=ws.id, title=MARKER, slug="s"))
    await db.flush()
    nb = add(
        m.Notebook(
            owner_id=o,
            subject_id=subject.id,
            title=MARKER,
            slug="nb",
            retrieval_settings={},
        )
    )
    await db.flush()
    note = add(m.Note(owner_id=o, notebook_id=nb.id, title=MARKER, content_md=MARKER))
    source = add(
        m.Source(
            owner_id=o, notebook_id=nb.id, kind=m.SourceKind.TXT, original_filename=MARKER
        )
    )
    concept = add(
        m.Concept(
            owner_id=o, workspace_id=ws.id, name=MARKER, normalized_name=MARKER.lower()
        )
    )
    other = add(
        m.Concept(owner_id=o, workspace_id=ws.id, name=MARKER + "2", normalized_name="x2")
    )
    await db.flush()
    edge = add(
        m.ConceptEdge(
            owner_id=o, src_id=concept.id, dst_id=other.id, kind=m.EdgeKind.RELATED_TO
        )
    )
    card = add(m.Card(owner_id=o, notebook_id=nb.id, front_md=MARKER, back_md=MARKER))
    question = add(
        m.Question(owner_id=o, notebook_id=nb.id, type=m.QuestionType.OPEN, prompt=MARKER)
    )
    await db.flush()
    answer = add(
        m.Answer(
            owner_id=o, question_id=question.id, response={"t": MARKER}, is_correct=False
        )
    )
    await db.flush()
    mistake = add(m.Mistake(owner_id=o, question_id=question.id, answer_id=answer.id))
    study = add(m.StudySession(owner_id=o, planned_minutes=10))
    exam = add(m.Exam(owner_id=o, notebook_id=nb.id, minutes=10))
    goal = add(
        m.Goal(owner_id=o, notebook_id=nb.id, title=MARKER, due_on=date(2030, 1, 1))
    )
    journey = add(m.LearningJourney(owner_id=o, goal=MARKER, subject=MARKER))
    await db.flush()
    teaching = add(
        m.TeachingSession(owner_id=o, journey_id=journey.id, learning_goal=MARKER)
    )
    summary = add(
        m.MemorySummary(
            owner_id=o, journey_id=journey.id, level="session", summary={"text": MARKER}
        )
    )
    assessment = add(m.Assessment(owner_id=o, journey_id=journey.id, kind="checkpoint"))
    credential = add(
        m.ProviderCredential(
            owner_id=o,
            provider="openai",
            label=MARKER,
            last4="1234",
            ciphertext=b"x",
            nonce=b"x",
            wrapped_key=b"x",
            wrapped_key_nonce=b"x",
        )
    )
    token = add(m.ApiToken(owner_id=o, name=MARKER, token_hash="0" * 64, scopes=["read"]))
    await db.flush()
    focus = add(
        m.FocusSession(
            owner_id=o,
            kind="learn",
            journey_id=journey.id,
            teaching_session_id=teaching.id,
            title=MARKER,
            concept=MARKER,
            planned_minutes=5,
            steps_total=2,
            started_at=utcnow(),
            last_activity_at=utcnow(),
        )
    )
    await db.flush()
    issued = await AuthService(db, Settings()).issue_session(alice)
    alice_session = await db.scalar(
        select(m.Session).where(m.Session.user_id == alice.id)
    )
    assert alice_session is not None
    _ = issued
    return {
        "workspace": ws,
        "subject": subject,
        "notebook": nb,
        "note": note,
        "source": source,
        "concept": concept,
        "edge": edge,
        "card": card,
        "question": question,
        "mistake": mistake,
        "answer": answer,
        "study": study,
        "exam": exam,
        "goal": goal,
        "journey": journey,
        "teaching": teaching,
        "summary": summary,
        "assessment": assessment,
        "credential": credential,
        "token": token,
        "focus": focus,
        "login": alice_session,
    }


def path_ids(alice: dict[str, Any], path: str) -> dict[str, str]:
    """Alice's id for every path parameter, by name and by route."""
    session_owner = (
        alice["teaching"]
        if "/ai/sessions/" in path
        else alice["study"]
        if "/learning-session/" in path
        else None
    )
    values: dict[str, Any] = {
        "workspace_id": alice["workspace"].id,
        "subject_id": alice["subject"].id,
        "notebook_id": alice["notebook"].id,
        "note_id": alice["note"].id,
        "source_id": alice["source"].id,
        "concept_id": alice["concept"].id,
        "edge_id": alice["edge"].id,
        "card_id": alice["card"].id,
        "question_id": alice["question"].id,
        "exam_id": alice["exam"].id,
        "mistake_id": alice["mistake"].id,
        "goal_id": alice["goal"].id,
        "credential_id": alice["credential"].id,
        "journey_id": alice["journey"].id,
        "summary_id": alice["summary"].id,
        "assessment_id": alice["assessment"].id,
        "token_id": alice["token"].id,
        "focus_id": alice["focus"].id,
        "target_user_id": alice["teaching"].owner_id,
        "session_id": session_owner.id if session_owner else alice["login"].family_id,
        "action": "summarize",
        "index": 0,
    }
    return {k: str(v) for k, v in values.items()}


def body_ids(alice: dict[str, Any]) -> dict[str, str]:
    """For `*_id` fields in a JSON body (and query strings)."""
    ids = path_ids(alice, "")
    ids["session_id"] = str(alice["teaching"].id)
    ids["src_id"] = str(alice["concept"].id)
    ids["dst_id"] = str(alice["edge"].dst_id)
    ids["answer_id"] = str(alice["answer"].id)
    return ids


def example(
    schema: dict[str, Any],
    spec: dict[str, Any],
    ids: dict[str, str],
    name: str = "",
    only: str | None = None,
) -> Any:
    """A minimal value that validates against `schema`, with Alice's id in the
    id field `only` names (every required id field too — it cannot be left
    out). Optional id fields other than `only` are omitted."""
    if "$ref" in schema:
        ref = schema["$ref"].rsplit("/", 1)[-1]
        return example(spec["components"]["schemas"][ref], spec, ids, name, only)
    for key in ("anyOf", "oneOf"):
        if key in schema:
            options = [s for s in schema[key] if s.get("type") != "null"]
            return example(options[0], spec, ids, name, only) if options else None
    if "allOf" in schema:
        return example(schema["allOf"][0], spec, ids, name, only)
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        required = set(schema.get("required", []))
        return {
            field: example(sub, spec, ids, field, only)
            for field, sub in schema.get("properties", {}).items()
            if field in required or field == only
        }
    if kind == "array":
        item = example(schema.get("items", {}), spec, ids, name.removesuffix("s"), only)
        return [item] * max(schema.get("minItems", 1), 1)
    if kind == "string":
        if name in ids:
            return ids[name]
        fmt = schema.get("format")
        if fmt == "uuid":
            return str(uuid.uuid4())
        if fmt == "date":
            return "2030-01-01"
        if fmt == "date-time":
            return "2030-01-01T00:00:00Z"
        if fmt == "email":
            return "bob@example.com"
        return "x" * max(schema.get("minLength", 1), 1)
    if kind == "integer":
        return max(schema.get("minimum", 1), 1)
    if kind == "number":
        return schema.get("minimum", 0.5)
    if kind == "boolean":
        return True
    return None


def _resolved(schema: dict[str, Any], spec: dict[str, Any], depth: int = 0) -> Any:
    if depth > 4:
        return {}
    if "$ref" in schema:
        ref = schema["$ref"].rsplit("/", 1)[-1]
        return _resolved(spec["components"]["schemas"][ref], spec, depth + 1)
    return {
        k: _resolved(v, spec, depth + 1) if isinstance(v, dict) else v
        for k, v in schema.items()
    }


def _is_id(field: str) -> bool:
    return field.endswith(("_id", "_ids"))


@dataclass
class Case:
    method: str
    path: str
    #: Which id of Alice's this request presents, for the failure message.
    probe: str
    query: dict[str, str] = field(default_factory=dict)
    json: Any = None
    form: dict[str, str] | None = None
    files: dict[str, tuple[str, bytes]] | None = None

    @property
    def label(self) -> str:
        return f"{self.method} {self.path} [{self.probe}]"


def _top_level(schema: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    """An object schema with its own `$ref` followed (one level only)."""
    if "$ref" in schema:
        return dict(spec["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]])
    return schema


def _build(
    op: dict[str, Any],
    method: str,
    path: str,
    probe: str,
    only: str | None,
    ids: dict[str, str],
    spec: dict[str, Any],
) -> Case:
    params = op.get("parameters", [])
    content = op.get("requestBody", {}).get("content", {})
    case = Case(method.upper(), path, probe)
    for p in params:
        if p["in"] != "query":
            continue
        if p["name"] == only:
            case.query[p["name"]] = ids[p["name"]]
        elif p.get("required"):
            case.query[p["name"]] = str(
                example(p.get("schema", {}), spec, ids, p["name"])
            )
    if "application/json" in content:
        case.json = example(content["application/json"]["schema"], spec, ids, only=only)
    if "multipart/form-data" in content:
        form = _top_level(content["multipart/form-data"]["schema"], spec)
        required = set(form.get("required", []))
        case.form, case.files = {}, {}
        for name, sub in form.get("properties", {}).items():
            if sub.get("format") == "binary" or "contentMediaType" in sub:
                case.files[name] = ("notes.txt", b"hello")
            elif name in required or name == only:
                case.form[name] = str(example(sub, spec, ids, name))
    return case


def cases(ids: dict[str, str]) -> list[Case]:
    """One request per id an operation accepts: the path's, and each query
    and body id on its own — so a route checking one id but trusting another
    is caught."""
    spec = app.openapi()
    out: list[Case] = []
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            if method not in {"get", "post", "patch", "put", "delete"}:
                continue
            content = op.get("requestBody", {}).get("content", {})
            names = [
                p["name"]
                for p in op.get("parameters", [])
                if p["in"] == "query" and _is_id(p["name"])
            ]
            for kind in ("application/json", "multipart/form-data"):
                if kind in content:
                    body = _top_level(content[kind]["schema"], spec)
                    names += [f for f in body.get("properties", {}) if _is_id(f)]
            if "{" in path:
                out.append(_build(op, method, path, "path", None, ids, spec))
            for name in names:
                if name in ids or name.removesuffix("s") in ids:
                    out.append(_build(op, method, path, name, name, ids, spec))
    return out


@pytest.fixture
async def bob_client(
    db: AsyncSession, other_user: m.User, settings: Settings
) -> AsyncIterator[httpx.AsyncClient]:
    issued = await AuthService(db, settings).issue_session(other_user)

    async def same_session() -> AsyncIterator[AsyncSession]:
        yield db

    app.dependency_overrides[get_session] = same_session
    # The app's Redis client outlives each test's event loop; a connection a
    # previous test opened would be bound to a closed loop. Start clean.
    redis = getattr(app.state, "redis", None)
    if redis is not None:
        await redis.connection_pool.disconnect()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={deps.SESSION_COOKIE: issued.refresh_token},
            headers={deps.CSRF_HEADER: issued.csrf_token},
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_session, None)
        if redis is not None:
            await redis.connection_pool.disconnect()


def test_the_sweep_covers_every_id_route() -> None:
    """A guard on the guard: the families the brief names are all present."""
    ids = {k: str(uuid.uuid4()) for k in ID_NAMES}
    swept = {c.path for c in cases(ids)}
    joined = " ".join(swept)
    for family in (
        "/ai/journeys/",
        "/ai/sessions/",
        "/ai/assessments/",
        "/ai/professor",
        "/exams/",
        "/questions/",
        "/mistakes/",
        "/cards/",
        "/reviews",
        "/notebooks/",
        "/notes/",
        "/sources",
        "/concepts/",
        "/concepts/edges/",
        "/goals/",
        "/memory",
        "/imports/",
    ):
        assert family in joined, family
    assert len(swept) >= 65


async def test_no_route_hands_alice_to_bob(
    db: AsyncSession, user: m.User, bob_client: httpx.AsyncClient
) -> None:
    alice = await build_alice(db, user)
    ids = body_ids(alice)
    spec = app.openapi()
    failures: list[str] = []

    for case in cases(ids):
        if case.label in NOT_JUDGED:
            continue
        url = case.path
        op = spec["paths"][case.path][case.method.lower()]
        for param in op.get("parameters", []):
            enum = _resolved(param.get("schema", {}), spec).get("enum")
            if param["in"] == "path" and enum:
                url = url.replace("{" + param["name"] + "}", str(enum[0]))
        for name, value in path_ids(alice, case.path).items():
            url = url.replace("{" + name + "}", value)
        assert "{" not in url, f"no value for a parameter of {case.path}"

        response = await bob_client.request(
            case.method,
            url,
            params=case.query,
            json=case.json if case.form is None else None,
            data=case.form,
            files=case.files or None,
        )
        status = response.status_code
        # A problem's `instance` echoes the path Bob asked for: his own input.
        text = response.text.replace(url, "")
        label = f"{case.label} -> {status}"

        if status >= 500:
            failures.append(f"{label} (server error)")
        elif MARKER in text or any(
            v in text for k, v in ids.items() if k not in {"action", "index"}
        ):
            failures.append(f"{label} LEAKS Alice's data: {text[:200]}")
        elif case.probe == "path" and status not in (403, 404):
            failures.append(f"{label} (expected 403/404): {text[:200]}")
        elif case.probe != "path" and case.method != "GET" and status not in (403, 404):
            # A write naming Alice's id must be refused for that reason, not
            # for some other one that would hide a missing check.
            failures.append(f"{label} (expected 403/404): {text[:200]}")
        elif (
            case.probe != "path"
            and case.method == "GET"
            and status
            not in (
                200,
                403,
                404,
            )
        ):
            failures.append(f"{label} (unexpected): {text[:200]}")

    assert not failures, "Cross-user isolation:\n  " + "\n  ".join(failures)

    # Nothing Bob tried changed anything of Alice's.
    for key, row in alice.items():
        model = type(row)
        if key == "login":
            still = await db.scalar(
                select(func.count())
                .select_from(m.Session)
                .where(m.Session.id == row.id, m.Session.revoked_at.is_(None))
            )
        else:
            still = await db.scalar(
                select(func.count()).select_from(model).where(model.id == row.id)
            )
        assert still == 1, f"Alice's {key} was removed or revoked by Bob"
