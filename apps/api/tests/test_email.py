"""noema.services.email -- Resend HTTP integration, mocked the same way every
provider in noema/providers/ is: a real httpx.MockTransport, not a stubbed-out
SDK, so the actual request shape is what's under test."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from noema.core.config import Settings
from noema.core.errors import FeatureUnavailable
from noema.services.email import send_email


def transport(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    )


async def test_raises_when_unconfigured(settings: Settings) -> None:
    settings.noema_resend_api_key = ""
    with pytest.raises(FeatureUnavailable, match="not configured"):
        await send_email(settings, to="a@example.com", subject="hi", html="<p>hi</p>")


async def test_sends_the_real_resend_request_shape(settings: Settings) -> None:
    settings.noema_resend_api_key = "re_test"
    settings.noema_email_from = "Noema <onboarding@resend.dev>"
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content
        return httpx.Response(200, json={"id": "email_123"})

    await send_email(
        settings,
        to="learner@example.com",
        subject="Redefinir sua senha",
        html="<p>link</p>",
        client=transport(handler),
    )

    assert b'"to":["learner@example.com"]' in captured["body"]
    assert b'"from":"Noema <onboarding@resend.dev>"' in captured["body"]


async def test_raises_on_a_real_resend_error_response(settings: Settings) -> None:
    settings.noema_resend_api_key = "re_test"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422, json={"name": "validation_error", "message": "Invalid `to` field"}
        )

    with pytest.raises(FeatureUnavailable):
        await send_email(
            settings,
            to="not-an-email",
            subject="hi",
            html="<p>hi</p>",
            client=transport(handler),
        )


async def test_raises_on_a_connection_failure(settings: Settings) -> None:
    settings.noema_resend_api_key = "re_test"

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(FeatureUnavailable):
        await send_email(
            settings,
            to="learner@example.com",
            subject="hi",
            html="<p>hi</p>",
            client=transport(handler),
        )
