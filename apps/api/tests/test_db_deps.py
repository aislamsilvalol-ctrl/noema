"""``get_gateway``'s own error translation, not the gateway it builds.

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
