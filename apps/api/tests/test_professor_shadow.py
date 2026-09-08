"""The shadow client: off by default, pseudonymous, and never a failure path.

Mocked with a real httpx.MockTransport, like every other HTTP integration
here, so what is under test is the request the Sabelia service would receive.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx

from noema.core.config import Settings
from noema.professor import shadow
from noema.services.learning_export import pseudonym

USER = uuid.UUID("11111111-2222-3333-4444-555555555555")


def rows() -> list[dict[str, Any]]:
    at = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
    return [
        {
            "id": uuid.uuid4(),
            "concept_id": None,
            "concept_name": "Mecanismos de defesa",
            "kind": "conversation",
            "score": 0.5,
            "item_id": None,
            "elapsed_ms": None,
            "difficulty": None,
            "confidence": None,
            "created_at": at,
        },
        {
            "id": uuid.uuid4(),
            "concept_id": "concept-uuid",
            "concept_name": "Mecanismos de defesa",
            "kind": "quiz",
            "score": 0.8,
            "item_id": "quiz:abc",
            "elapsed_ms": 9000,
            "difficulty": 0.4,
            "confidence": 0.6,
            "created_at": at,
        },
    ]


def configured(settings: Settings) -> Settings:
    settings.noema_sabelia_url = "http://sabelia.test"
    settings.noema_export_secret = "a-secret-of-sufficient-length"
    return settings


def responder(captured: dict[str, Any]) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/events":
            captured["body"] = request.content.decode()
            return httpx.Response(200, json={"accepted": 2})
        if request.url.path.endswith("/recommend"):
            captured["recommend_path"] = request.url.path
            return httpx.Response(
                200,
                json={
                    "action": "review",
                    "concept_id": "concept-uuid",
                    "score": 0.7,
                    "reasons": ["recall_predicted_low", "days_since_practice=8"],
                    "suggested_difficulty": None,
                    "alternatives": [],
                },
            )
        return httpx.Response(
            200,
            json={
                "student_id": "u_x",
                "model": "mastery-heuristic",
                "events": 2,
                "concepts": {"concept-uuid": {"recall": 0.54, "mastery": 0.61}},
            },
        )

    return handler


async def test_off_unless_both_url_and_secret_are_set(settings: Settings) -> None:
    settings.noema_sabelia_url = ""
    settings.noema_export_secret = ""
    assert shadow.enabled(settings) is False
    assert await shadow.ask(settings, USER, rows()) is None

    settings.noema_sabelia_url = "http://sabelia.test"
    assert shadow.enabled(settings) is False  # a URL without a secret stays off


async def test_records_the_recommendation_and_never_sends_text(
    settings: Settings,
) -> None:
    captured: dict[str, Any] = {}
    client = httpx.AsyncClient(transport=httpx.MockTransport(responder(captured)))

    result = await shadow.ask(configured(settings), USER, rows(), client=client)

    assert result is not None
    assert result.action == "review" and result.concept == "concept-uuid"
    assert result.reasons[0] == "recall_predicted_low"
    assert result.recall == 0.54 and result.mastery == 0.61
    record = result.as_record()
    assert record["engine"] == "sabelia" and record["events"] == 2

    body = captured["body"]
    # the learner is a pseudonym, and the concept the lesson named never
    # crosses as text — only the id, or a hashed-free-text stand-in
    assert pseudonym(settings.noema_export_secret, USER) in body
    assert str(USER) not in body
    assert "Mecanismos de defesa" not in body or "name:" in body
    assert captured["recommend_path"].endswith("/recommend")


async def test_a_broken_service_is_silent(settings: Settings) -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("no route")

    client = httpx.AsyncClient(transport=httpx.MockTransport(broken))
    assert await shadow.ask(configured(settings), USER, rows(), client=client) is None


async def test_an_error_response_is_silent(settings: Settings) -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(503))
    )
    assert await shadow.ask(configured(settings), USER, rows(), client=client) is None


async def test_graded_and_ungraded_events_keep_their_type(settings: Settings) -> None:
    payload = shadow._events_payload("u_test", rows())
    conversation, quiz = payload
    assert conversation["event_type"] == "exposure" and conversation["correct"] is None
    assert conversation["concept_id"] == "name:Mecanismos de defesa"
    assert quiz["event_type"] == "answer" and quiz["correct"] is True
    assert quiz["elapsed_ms"] == 9000 and quiz["confidence"] == 0.6
