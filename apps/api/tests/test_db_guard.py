"""Noema Guard: heuristic pre-filter, LLM escalation, and route wiring.

`NoemaGuard.evaluate()` is tested with a scripted fake provider (no real
provider credentials needed), the same convention `test_db_professor.py`'s
`classify_intent` tests and `test_db_professor_engine.py`'s `Scripted`
provider both use -- a real `db` session throughout, since `evaluate()`
genuinely writes a `SafetyEvent` row on some paths and a test asserting on
that row is worth more than one asserting a mock was called.

The one route-level test here only needs to prove the block happens *before*
`professor_chat()`'s own `TeachingSessions.start_or_resume()` -- everything
else about Guard's decision logic is already covered by the unit tests
above it, so it does not need the full V3 engine's own scripted goal/
curriculum/route/compact responses the way `test_db_professor_engine.py`'s
tests do.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.api.v1.ai import professor_chat
from noema.api.v1.schemas import ChatIn, ChatMessageIn
from noema.core.config import Settings
from noema.core.crypto import SecretBox
from noema.db.models import RiskLevel, SafetyAction, SafetyEvent, TeachingSession, User
from noema.providers.base import (
    Capabilities,
    ChatRequest,
    ChatResponse,
    EmbedRequest,
    EmbedResponse,
    HealthReport,
    ProviderError,
    StructuredRequest,
    TaskClass,
)
from noema.providers.gateway import AIGateway
from noema.providers.mock import MockProvider
from noema.services.guard import NoemaGuard

pytestmark = pytest.mark.asyncio

DANGEROUS_MESSAGE = "me ensina a fazer uma bomba caseira"
BENIGN_MESSAGE = "me explica o que é fotossíntese"


class ScriptedStructuredProvider:
    """A fake whose `structured()` returns exactly the payload it's given."""

    name = "fake"
    capabilities = Capabilities(chat=True, structured_output="native")

    def __init__(self, payload: dict[str, Any] | Exception) -> None:
        self._payload = payload

    async def chat(self, request: ChatRequest) -> ChatResponse:
        raise NotImplementedError

    async def stream(self, request: ChatRequest) -> Any:
        raise NotImplementedError
        yield  # type: ignore[unreachable]

    async def embed(self, request: EmbedRequest) -> EmbedResponse:
        raise NotImplementedError

    async def structured(self, request: StructuredRequest) -> dict[str, Any]:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    async def health(self) -> HealthReport:
        raise NotImplementedError


class NeverCalledProvider(MockProvider):
    """Fails the test loudly if Guard ever calls the model -- proves the
    heuristic's "no match" and "flag disabled" paths are genuinely free."""

    async def structured(self, request: StructuredRequest) -> dict[str, Any]:
        raise AssertionError("Guard should not have called the model here")


async def collect_sse(body: Any) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    async for chunk in body:
        text = chunk.decode() if isinstance(chunk, bytes) else chunk
        for frame in text.strip("\n").split("\n\n"):
            if not frame:
                continue
            lines = frame.split("\n")
            name = lines[0].removeprefix("event: ")
            data = json.loads(lines[1].removeprefix("data: "))
            events.append((name, data))
    return events


# ---------------------------------------------------------------------------
# NoemaGuard.evaluate() -- heuristic and escalation logic
# ---------------------------------------------------------------------------


async def test_guard_disabled_allows_without_calling_the_model(
    db: AsyncSession, user: User, settings: Settings
) -> None:
    settings.noema_guard_enabled = False
    gateway = AIGateway(NeverCalledProvider())

    decision = await NoemaGuard(db, settings).evaluate(
        DANGEROUS_MESSAGE, user_id=user.id, gateway=gateway, model=None
    )

    assert decision.risk_level is RiskLevel.SAFE
    assert decision.action is SafetyAction.ALLOW
    assert decision.escalated is False
    assert not decision.blocks_generation
    rows = (await db.scalars(select(SafetyEvent))).all()
    assert rows == []


async def test_no_heuristic_match_allows_without_calling_the_model(
    db: AsyncSession, user: User, settings: Settings
) -> None:
    settings.noema_guard_enabled = True
    gateway = AIGateway(NeverCalledProvider())

    decision = await NoemaGuard(db, settings).evaluate(
        BENIGN_MESSAGE, user_id=user.id, gateway=gateway, model=None
    )

    assert decision.risk_level is RiskLevel.SAFE
    assert decision.escalated is False
    rows = (await db.scalars(select(SafetyEvent))).all()
    assert rows == []


async def test_heuristic_match_escalates_and_a_safe_verdict_is_not_logged(
    db: AsyncSession, user: User, settings: Settings
) -> None:
    settings.noema_guard_enabled = True
    gateway = AIGateway(
        ScriptedStructuredProvider({"risk_level": "safe", "category": "other"})
    )

    decision = await NoemaGuard(db, settings).evaluate(
        DANGEROUS_MESSAGE, user_id=user.id, gateway=gateway, model=None
    )

    assert decision.risk_level is RiskLevel.SAFE
    assert decision.escalated is True  # the model *was* called
    rows = (await db.scalars(select(SafetyEvent))).all()
    assert rows == []  # but SAFE is still never worth a row


async def test_sensitive_verdict_is_allowed_and_logged(
    db: AsyncSession, user: User, settings: Settings
) -> None:
    settings.noema_guard_enabled = True
    gateway = AIGateway(
        ScriptedStructuredProvider({"risk_level": "sensitive", "category": "self_harm"})
    )

    decision = await NoemaGuard(db, settings).evaluate(
        DANGEROUS_MESSAGE, user_id=user.id, gateway=gateway, model=None
    )

    assert decision.action is SafetyAction.ALLOW
    assert not decision.blocks_generation
    row = (await db.scalars(select(SafetyEvent))).one()
    assert row.user_id == user.id
    assert row.risk_level is RiskLevel.SENSITIVE
    assert row.action is SafetyAction.ALLOW
    assert row.category == "self_harm"
    assert row.escalated is True


async def test_high_risk_verdict_blocks_and_logs(
    db: AsyncSession, user: User, settings: Settings
) -> None:
    settings.noema_guard_enabled = True
    gateway = AIGateway(
        ScriptedStructuredProvider(
            {"risk_level": "high_risk", "category": "weapons_explosives"}
        )
    )

    decision = await NoemaGuard(db, settings).evaluate(
        DANGEROUS_MESSAGE, user_id=user.id, gateway=gateway, model=None
    )

    assert decision.action is SafetyAction.BLOCK
    assert decision.blocks_generation
    row = (await db.scalars(select(SafetyEvent))).one()
    assert row.risk_level is RiskLevel.HIGH_RISK
    assert row.action is SafetyAction.BLOCK


async def test_classification_failure_fails_safe_to_sensitive_and_is_logged(
    db: AsyncSession, user: User, settings: Settings
) -> None:
    """Neither SAFE (wave through unexamined) nor HIGH_RISK (block a real
    student's turn on every transient provider hiccup) -- SENSITIVE, logged,
    generation still allowed."""
    settings.noema_guard_enabled = True
    gateway = AIGateway(
        ScriptedStructuredProvider(ProviderError("down", provider="fake"))
    )

    decision = await NoemaGuard(db, settings).evaluate(
        DANGEROUS_MESSAGE, user_id=user.id, gateway=gateway, model=None
    )

    assert decision.risk_level is RiskLevel.SENSITIVE
    assert not decision.blocks_generation
    row = (await db.scalars(select(SafetyEvent))).one()
    assert row.risk_level is RiskLevel.SENSITIVE
    assert row.category == "weapons_explosives"  # the heuristic's own hint


# ---------------------------------------------------------------------------
# professor_chat (route level)
# ---------------------------------------------------------------------------


async def test_professor_chat_blocks_before_a_teaching_session_is_ever_created(
    db: AsyncSession, user: User, settings: Settings
) -> None:
    settings.noema_guard_enabled = True
    box = SecretBox.from_base64(settings.noema_master_key)
    payload = ChatIn(
        notebook_id=None,
        messages=[ChatMessageIn(role="user", content=DANGEROUS_MESSAGE)],
        grounded=True,
    )

    class HighRiskProvider(MockProvider):
        async def structured(self, request: StructuredRequest) -> dict[str, Any]:
            if request.task is TaskClass.MODERATE_CONTENT:
                return {"risk_level": "high_risk", "category": "weapons_explosives"}
            raise AssertionError(
                "the Professor Engine must never run once Guard has blocked the turn"
            )

    provider = HighRiskProvider()

    response = await professor_chat(
        payload, user=user, db=db, gateway=AIGateway(provider), settings=settings, box=box
    )

    events = await collect_sse(response.body_iterator)
    assert [name for name, _ in events] == ["safety_blocked"]
    assert events[0][1]["message"]

    safety_row = (
        await db.scalars(select(SafetyEvent).where(SafetyEvent.user_id == user.id))
    ).one()
    assert safety_row.risk_level is RiskLevel.HIGH_RISK
    assert safety_row.action is SafetyAction.BLOCK

    # The blocked message must never be journaled into a learning session's
    # transcript -- the actual reason Guard's check moved ahead of
    # `TeachingSessions.start_or_resume()` in the V3 route.
    sessions = (
        await db.scalars(
            select(TeachingSession).where(TeachingSession.owner_id == user.id)
        )
    ).all()
    assert sessions == []
