"""``get_gateway``'s own error translation, and the chain it builds.

``build_provider`` raising ``ProviderError`` (no deployment key, no BYOK key,
for the resolved provider) must never reach a route as a bare, untranslated
exception -- ``ProviderError`` is not a ``NoemaError``, so FastAPI's registered
error handlers never see it and it would otherwise fall through as a generic
500 with no honest message.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from noema.api.v1 import deps
from noema.core.config import Settings
from noema.core.crypto import SecretBox
from noema.core.errors import ProviderUnavailable
from noema.db.models import User
from noema.providers.base import ProviderError

pytestmark = pytest.mark.asyncio


def _request() -> Request:
    # Never reaches request.app.state -- build_provider raises before that
    # line, so a minimal ASGI scope is enough.
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/ai/chat",
        "query_string": b"",
        "headers": [],
    }
    return Request(scope)


async def test_a_provider_error_from_build_provider_becomes_provider_unavailable(
    db: AsyncSession,
    user: User,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_build_provider(
        name: str, settings_: Settings, credentials: Any
    ) -> None:
        raise ProviderError("Anthropic API key is required", provider=name)

    monkeypatch.setattr(deps, "build_provider", fake_build_provider)

    box = SecretBox.from_base64(settings.noema_master_key)
    router = deps.get_router(settings)

    with pytest.raises(ProviderUnavailable):
        await deps.get_gateway(
            request=_request(),
            user=user,
            db=db,
            settings=settings,
            box=box,
            router=router,
        )



# ── the fallback chain ────────────────────────────────────────────────────
#
# A deployment that configures a second key expects it to be used: when the
# default provider answers "your credit balance is too low" -- a 400, which
# the gateway will not retry -- the lesson has to continue somewhere. Before
# this, `_gateway` built `AIGateway(primary)` with no fallbacks at all, so a
# configured OPENAI_API_KEY sat unused while every lesson failed.


async def test_the_chain_holds_every_other_configured_provider() -> None:
    settings = Settings(
        noema_default_provider="anthropic",
        anthropic_api_key="sk-ant-test",
        openai_api_key="sk-openai-test",
    )

    chain = await deps._fallback_chain("anthropic", settings, credentials=None)

    assert [p.name for p in chain] == ["openai"]


async def test_a_provider_without_a_key_is_not_in_the_chain() -> None:
    settings = Settings(
        noema_default_provider="anthropic",
        anthropic_api_key="sk-ant-test",
    )

    chain = await deps._fallback_chain("anthropic", settings, credentials=None)

    assert chain == []


async def test_the_primary_is_never_its_own_fallback() -> None:
    settings = Settings(
        noema_default_provider="openai",
        anthropic_api_key="sk-ant-test",
        openai_api_key="sk-openai-test",
    )

    chain = await deps._fallback_chain("openai", settings, credentials=None)

    assert [p.name for p in chain] == ["anthropic"]
