"""Bounds on what a request may hand to a model, and what a deployment shows.

Every field here goes into a prompt more or less verbatim, so its length is a
cost the caller sets. The caps are wide enough for any honest use and small
enough that no single request can be expensive on its own.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from noema.api.v1.study import ClozeCreate, ExplanationIn, SocraticIn
from noema.core.config import get_settings
from noema.main import app, create_app

CONCEPT = uuid.uuid4()


def test_an_explanation_is_capped_at_8000_characters() -> None:
    ExplanationIn(concept_id=CONCEPT, text="x" * 8_000)
    with pytest.raises(ValidationError):
        ExplanationIn(concept_id=CONCEPT, text="x" * 8_001)


def test_a_cloze_passage_is_capped_at_8000_characters() -> None:
    ClozeCreate(notebook_id=CONCEPT, text="{{c1::x}}" * 800)
    with pytest.raises(ValidationError):
        ClozeCreate(notebook_id=CONCEPT, text="x" * 8_001)


def test_a_socratic_transcript_is_at_most_40_turns_of_4000_characters() -> None:
    turn = {"role": "learner", "content": "x" * 4_000}
    SocraticIn(concept_id=CONCEPT, transcript=[turn] * 40)

    with pytest.raises(ValidationError):
        SocraticIn(concept_id=CONCEPT, transcript=[turn] * 41)
    with pytest.raises(ValidationError):
        SocraticIn(
            concept_id=CONCEPT, transcript=[{"role": "learner", "content": "x" * 4_001}]
        )


def test_the_search_query_is_capped_at_2000_characters() -> None:
    """Asserted on the schema: FastAPI refuses the request before the route,
    the retrieval and the embedding call it would have paid for."""
    parameters = app.openapi()["paths"]["/api/v1/search"]["get"]["parameters"]
    q = next(p for p in parameters if p["name"] == "q")

    assert q["schema"]["maxLength"] == 2_000


def test_the_api_schema_and_docs_are_not_served_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NOEMA_ENV", "production")
    get_settings.cache_clear()

    production = create_app()

    assert production.openapi_url is None
    assert production.docs_url is None
    assert production.redoc_url is None
    client = TestClient(production)
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
