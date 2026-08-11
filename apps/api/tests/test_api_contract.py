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
