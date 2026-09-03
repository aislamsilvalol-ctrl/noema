"""Transactional email via Resend.

Uses the HTTP API directly, the same "no vendor SDK for a small, stable REST
surface" choice `noema/providers/anthropic.py` already makes -- one fewer
dependency, and the wire format is small enough that the indirection would
cost more than it saves.

Fails closed with `FeatureUnavailable` when `NOEMA_RESEND_API_KEY` is unset,
matching `noema/services/billing.py`'s own discipline: every email-sending
route checks this explicitly rather than crashing on a missing credential,
which is the actual state of a fresh deployment until an operator configures
a real key.
"""

from __future__ import annotations

import httpx

from noema.core.config import Settings
from noema.core.errors import FeatureUnavailable
from noema.core.logging import get_logger

log = get_logger(__name__)

RESEND_API = "https://api.resend.com"


async def send_email(
    settings: Settings,
    *,
    to: str,
    subject: str,
    html: str,
    client: httpx.AsyncClient | None = None,
) -> None:
    """``client`` is injectable the same way every provider in
    ``noema/providers/`` accepts one -- a real ``httpx.MockTransport`` in
    tests, a real client in production."""
    if not settings.noema_resend_api_key:
        raise FeatureUnavailable(
            "Email delivery is not configured on this deployment. "
            "Set NOEMA_RESEND_API_KEY to enable it."
        )

    owns_client = client is None
    client = client or httpx.AsyncClient(
        base_url=RESEND_API,
        headers={"authorization": f"Bearer {settings.noema_resend_api_key}"},
        timeout=15.0,
    )
    try:
        try:
            response = await client.post(
                "/emails",
                json={
                    "from": settings.noema_email_from,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                },
            )
        except httpx.HTTPError as exc:
            log.warning("email.send_failed", error=str(exc))
            raise FeatureUnavailable("Could not send email right now.") from exc

        if not response.is_success:
            # Resend's error body is a small JSON object -- safe to log (no
            # secrets in it, same reasoning as the Anthropic/OpenAI provider
            # error-body logging), and it's the only way to tell a bad
            # template from a bad key from a bounced address without guessing.
            log.warning(
                "email.send_failed", status=response.status_code, body=response.text[:500]
            )
            raise FeatureUnavailable("Could not send email right now.")
    finally:
        if owns_client:
            await client.aclose()
