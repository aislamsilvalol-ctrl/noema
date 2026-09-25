"""A security receipt never undoes the change it reports."""

from __future__ import annotations

import pytest

from noema.core.config import Settings
from noema.services import security_notice

pytestmark = pytest.mark.asyncio


async def test_an_unconfigured_mailer_is_logged_not_raised() -> None:
    settings = Settings(noema_resend_api_key="")
    await security_notice.notify(settings, "ana@example.com", "password_changed")


async def test_every_event_has_words_and_the_way_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, str]] = []

    async def fake_send(_settings: Settings, **kwargs: str) -> None:
        sent.append(kwargs)

    monkeypatch.setattr(security_notice, "send_email", fake_send)
    settings = Settings()
    for event in ("password_changed", "password_reset", "mfa_enabled", "mfa_disabled"):
        await security_notice.notify(settings, "ana@example.com", event)

    assert len(sent) == 4
    assert all("/forgot-password" in mail["html"] for mail in sent)
    assert len({mail["subject"] for mail in sent}) == 4
