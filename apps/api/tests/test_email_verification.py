"""Email verification without a database: the email that never fails a
registration, and the gate that stays closed until an operator opens it."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.requests import Request

from noema.api.v1 import deps
from noema.core.config import Settings
from noema.core.crypto import SecretBox
from noema.core.errors import EmailNotVerified, PlanLimitReached
from noema.services import email_verification
from noema.services.entitlements import EntitlementCheck

pytestmark = pytest.mark.asyncio


# ── the email ──────────────────────────────────────────────────────────────


async def test_an_unconfigured_mailer_is_logged_not_raised() -> None:
    settings = Settings(noema_resend_api_key="")
    await email_verification.send_verification_email(
        settings, "ana@example.com", "a-token"
    )


async def test_the_email_carries_the_link_and_nothing_is_logged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, str]] = []

    async def fake_send(_settings: Settings, **kwargs: str) -> None:
        sent.append(kwargs)

    monkeypatch.setattr(email_verification, "send_email", fake_send)
    settings = Settings(noema_web_origin="https://app.example.com")

    await email_verification.send_verification_email(
        settings, "ana@example.com", "tok-123"
    )

    assert len(sent) == 1
    assert sent[0]["to"] == "ana@example.com"
    assert "https://app.example.com/verify-email?token=tok-123" in sent[0]["html"]


async def test_a_mail_provider_failure_never_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def broken(_settings: Settings, **kwargs: str) -> None:
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(email_verification, "send_email", broken)

    await email_verification.send_verification_email(Settings(), "ana@example.com", "tok")


# ── the gate ───────────────────────────────────────────────────────────────


def _request() -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/ai/chat",
        "query_string": b"",
        "headers": [],
    }
    return Request(scope)


def _blocked_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    """The check right after the verification gate, scripted to refuse, so a
    test can tell "passed the gate" (402) from "stopped at it" (403)."""

    class Scripted:
        def __init__(self, db: Any, user: Any) -> None:
            pass

        async def check_ai_usage(self) -> EntitlementCheck:
            return EntitlementCheck(
                allowed=False, warn=False, used_units=50, limit_units=50
            )

    monkeypatch.setattr(deps, "EntitlementsService", Scripted)


async def _gateway(user: Any, settings: Settings) -> None:
    await deps.get_gateway(
        request=_request(),
        user=user,
        db=None,  # type: ignore[arg-type]
        settings=settings,
        box=SecretBox.from_base64(settings.noema_master_key),
        router=deps.get_router(settings),
    )


def test_the_gate_is_off_by_default() -> None:
    assert Settings().noema_require_verified_email_for_ai is False


async def test_off_an_unverified_account_passes_the_gate(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _blocked_plan(monkeypatch)
    unverified = SimpleNamespace(id=uuid.uuid4(), email_verified_at=None)

    with pytest.raises(PlanLimitReached):
        await _gateway(unverified, settings)


async def test_on_an_unverified_account_is_refused_with_its_own_slug(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _blocked_plan(monkeypatch)
    strict = Settings(noema_require_verified_email_for_ai=True)
    unverified = SimpleNamespace(id=uuid.uuid4(), email_verified_at=None)

    with pytest.raises(EmailNotVerified) as caught:
        await _gateway(unverified, strict)

    problem = caught.value.to_problem("/api/v1/ai/chat")
    assert problem["status"] == 403
    assert problem["type"].endswith("/email-not-verified")


async def test_on_a_verified_account_passes_the_gate(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime

    _blocked_plan(monkeypatch)
    strict = Settings(noema_require_verified_email_for_ai=True)
    verified = SimpleNamespace(id=uuid.uuid4(), email_verified_at=datetime.now(UTC))

    with pytest.raises(PlanLimitReached):
        await _gateway(verified, strict)
