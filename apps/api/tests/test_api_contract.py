"""Contract tests over the generated OpenAPI document.

These enforce promises made in the README and SECURITY.md at the schema level, where
they cannot drift out of sync with the code the way prose does.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from noema.main import app

SECRET_FIELD_NAMES = {
    "api_key",
    "apikey",
    "password_hash",
    "ciphertext",
    "nonce",
    "wrapped_key",
    "wrapped_key_nonce",
    "refresh_token",
    "master_key",
}

# Schemas that legitimately accept a secret as *input*. Nothing here may be used as
# a response model.
WRITE_ONLY_SCHEMAS = {"CredentialCreate", "RegisterRequest", "LoginRequest"}


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    return app.openapi()


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_openapi_is_3_1(spec: dict[str, Any]) -> None:
    assert spec["openapi"].startswith("3.1")


def test_no_response_schema_can_carry_a_secret(spec: dict[str, Any]) -> None:
    """The structural version of 'no endpoint returns an API key'."""
    schemas = spec["components"]["schemas"]
    offenders: list[str] = []

    for path, operations in spec["paths"].items():
        for method, operation in operations.items():
            if method not in {"get", "post", "patch", "put", "delete"}:
                continue
            for status_code, response in operation.get("responses", {}).items():
                content = response.get("content", {}).get("application/json", {})
                for name in _referenced_schemas(content.get("schema", {}), schemas):
                    if name in WRITE_ONLY_SCHEMAS:
                        offenders.append(
                            f"{method.upper()} {path} {status_code} → {name}"
                        )
                        continue
                    fields = set(schemas.get(name, {}).get("properties", {}))
                    leaked = fields & SECRET_FIELD_NAMES
                    if leaked:
                        offenders.append(
                            f"{method.upper()} {path} {status_code} → {name}{leaked}"
                        )

    assert not offenders, "Response schemas exposing secrets:\n  " + "\n  ".join(
        offenders
    )


def test_credential_responses_expose_only_the_last_four(spec: dict[str, Any]) -> None:
    fields = set(spec["components"]["schemas"]["CredentialOut"]["properties"])
    assert "last4" in fields
    assert not fields & SECRET_FIELD_NAMES


def test_every_mutation_is_csrf_protected(spec: dict[str, Any]) -> None:
    """Auth endpoints establish a session and are exempt; everything else is not."""
    from noema.api.v1 import ai, library
    from noema.api.v1.deps import require_csrf

    for router in (ai.router, library.router):
        dependency_calls = [d.dependency for d in router.dependencies]
        assert require_csrf in dependency_calls, (
            f"{router.prefix!r} is missing CSRF protection"
        )


def test_health_needs_no_authentication(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_protected_endpoints_reject_anonymous_callers(client: TestClient) -> None:
    for path in ("/api/v1/workspaces", "/api/v1/notebooks", "/api/v1/ai/providers"):
        response = client.get(path)
        assert response.status_code == 401, path
        assert response.headers["content-type"].startswith("application/problem+json")


def test_meta_is_public_and_says_what_this_deployment_is(client: TestClient) -> None:
    """The sign-in page needs this before there is anyone to authenticate.

    It must also never grow a secret: the assertion below fails the moment a key,
    a URL or a token is added to the response.
    """
    body = client.get("/api/v1/meta").json()

    assert set(body) == {
        "mode",
        "local",
        "allow_signups",
        "default_provider",
        "embedding_model",
        "version",
        # The commit this build came from. Public deliberately: the repository is
        # AGPL and every revision is already readable, and the alternative — an
        # instance that cannot say which code it runs — is what let production
        # serve two-day-old code unnoticed.
        "revision",
    }
    assert isinstance(body["local"], bool)


def test_errors_are_problem_details(client: TestClient) -> None:
    body = client.get("/api/v1/workspaces").json()
    assert set(body) >= {"type", "title", "status", "detail", "instance"}
    assert body["type"].startswith("https://noema.dev/errors/")


def test_validation_errors_name_the_offending_fields(client: TestClient) -> None:
    response = client.post("/api/v1/auth/register", json={"email": "not-an-email"})
    assert response.status_code == 422
    body = response.json()
    assert body["title"] == "Validation failed"
    assert {e["field"] for e in body["errors"]} >= {"email"}


def test_security_headers_are_present(client: TestClient) -> None:
    headers = client.get("/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert "x-request-id" in headers


def _referenced_schemas(
    node: Any, schemas: dict[str, Any], seen: set[str] | None = None
) -> set[str]:
    """Every schema name reachable from a response body, following $ref and unions."""
    seen = seen if seen is not None else set()
    if isinstance(node, dict):
        ref = node.get("$ref", "")
        if ref.startswith("#/components/schemas/"):
            name = ref.rsplit("/", 1)[-1]
            if name not in seen:
                seen.add(name)
                _referenced_schemas(schemas.get(name, {}), schemas, seen)
        for value in node.values():
            _referenced_schemas(value, schemas, seen)
    elif isinstance(node, list):
        for item in node:
            _referenced_schemas(item, schemas, seen)
    return seen


def test_spec_is_serialisable(spec: dict[str, Any]) -> None:
    """The TypeScript client is generated from this document in CI."""
    assert json.dumps(spec)


# ── What a question is allowed to tell the client ────────────────────────────


def test_a_question_never_ships_its_own_answer() -> None:
    """The client gets what it needs to answer and nothing that answers.

    Arrangement types are the trap: strip an ordering question's `order` and there
    is nothing left to render, so the items are sent shuffled instead. If that
    shuffle were seeded by anything the client holds, it could be inverted straight
    back into the answer.
    """
    import uuid as _uuid

    from noema.api.v1.study import _public_payload
    from noema.db.models import Difficulty, Question, QuestionType

    steps = ["depolarise", "plateau", "repolarise", "rest"]

    def question_with(question_id: _uuid.UUID) -> Question:
        return Question(
            id=question_id,
            owner_id=_uuid.uuid4(),
            notebook_id=_uuid.uuid4(),
            concept_id=None,
            type=QuestionType.ORDERING,
            difficulty=Difficulty.MEDIUM,
            prompt="Put the phases in order",
            payload={"order": steps, "explanation": "phases of the action potential"},
        )

    # The permutation is seeded from the question id (deterministic, not re-rolled
    # per call — see _shuffled's own docstring), so a single random id has a real
    # 1-in-24 chance of landing back on the original order. Try a few ids rather
    # than asserting on one that might have, by luck, come out unshuffled.
    question = question_with(_uuid.uuid4())
    public = _public_payload(question)
    for _ in range(9):
        if public["items"] != steps:
            break
        question = question_with(_uuid.uuid4())
        public = _public_payload(question)

    assert "order" not in public, "the correct sequence was sent to the client"
    assert sorted(public["items"]) == sorted(steps), "the items are not the same set"
    assert public["items"] != steps, "no shuffled id was found in 10 attempts"
    assert public["explanation"] == "phases of the action potential"

    # Stable, or a reload rearranges work in progress.
    assert _public_payload(question)["items"] == public["items"]


def test_a_matching_question_does_not_ship_its_pairs() -> None:
    """`pairs` is the answer key; it used to go out with the question."""
    import uuid as _uuid

    from noema.api.v1.study import _public_payload
    from noema.db.models import Difficulty, Question, QuestionType

    pairs = {"Preload": "end-diastolic volume", "Afterload": "resistance"}
    question = Question(
        id=_uuid.uuid4(),
        owner_id=_uuid.uuid4(),
        notebook_id=_uuid.uuid4(),
        concept_id=None,
        type=QuestionType.MATCHING,
        difficulty=Difficulty.MEDIUM,
        prompt="Match them",
        payload={"pairs": pairs},
    )

    public = _public_payload(question)

    assert "pairs" not in public
    assert public["left"] == list(pairs)
    assert sorted(public["right"]) == sorted(pairs.values())
