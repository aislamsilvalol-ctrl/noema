"""BillingService: checkout, the customer portal, and idempotent webhooks.

Every Stripe SDK call is mocked -- CI has no real Stripe key, and none of these
tests should ever make a network call. `_client` and `stripe.Webhook.
construct_event` are the two seams `noema.services.billing` exposes for that;
tests patch exactly those, never the SDK's own HTTP layer.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.config import Settings
from noema.core.errors import Conflict, FeatureUnavailable
from noema.db.models import Plan, StripeEvent, User
from noema.services.billing import BillingService

pytestmark = pytest.mark.asyncio


def _configure_billing(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    monkeypatch.setattr(settings, "noema_stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(settings, "noema_stripe_webhook_secret", "whsec_fake")
    monkeypatch.setattr(settings, "noema_stripe_price_student", "price_student")
    monkeypatch.setattr(settings, "noema_stripe_price_pro", "price_pro")
    monkeypatch.setattr(settings, "noema_stripe_price_max", "price_max")
    monkeypatch.setattr(settings, "noema_cors_origins", "https://app.noema.dev")


class _FakeCheckoutSessions:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create_async(self, params: dict[str, Any]) -> SimpleNamespace:
        self.calls.append(params)
        return SimpleNamespace(url="https://checkout.stripe.com/fake-session")


class _FakePortalSessions:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create_async(self, params: dict[str, Any]) -> SimpleNamespace:
        self.calls.append(params)
        return SimpleNamespace(url="https://billing.stripe.com/fake-portal")


class _FakeClient:
    def __init__(self) -> None:
        self.checkout_sessions = _FakeCheckoutSessions()
        self.portal_sessions = _FakePortalSessions()
        self.v1 = SimpleNamespace(
            checkout=SimpleNamespace(sessions=self.checkout_sessions),
            billing_portal=SimpleNamespace(sessions=self.portal_sessions),
        )


def _patch_client(monkeypatch: pytest.MonkeyPatch) -> _FakeClient:
    fake = _FakeClient()
    monkeypatch.setattr("noema.services.billing._client", lambda settings: fake)
    return fake


def _checkout_completed_event(
    *, event_id: str, user_id: str, plan: str, customer_id: str = "cus_123"
) -> dict[str, Any]:
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": user_id,
                "customer": customer_id,
                "metadata": {"noema_user_id": user_id, "noema_plan": plan},
            }
        },
    }


def _subscription_deleted_event(*, event_id: str, user_id: str) -> dict[str, Any]:
    return {
        "id": event_id,
        "type": "customer.subscription.deleted",
        "data": {
            "object": {"metadata": {"noema_user_id": user_id}, "status": "canceled"}
        },
    }


async def test_checkout_calls_stripe_with_the_right_price_and_metadata(
    db: AsyncSession, settings: Settings, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_billing(monkeypatch, settings)
    fake = _patch_client(monkeypatch)

    url = await BillingService(db=db, settings=settings).create_checkout_session(
        user=user, plan=Plan.PRO, request_origin=None
    )

    assert url == "https://checkout.stripe.com/fake-session"
    [call] = fake.checkout_sessions.calls
    assert call["line_items"] == [{"price": "price_pro", "quantity": 1}]
    assert call["client_reference_id"] == str(user.id)
    assert call["metadata"]["noema_user_id"] == str(user.id)
    assert call["metadata"]["noema_plan"] == "pro"
    assert call["customer_email"] == user.email
    assert call["success_url"].startswith("https://app.noema.dev")


async def test_checkout_reuses_an_existing_stripe_customer(
    db: AsyncSession, settings: Settings, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_billing(monkeypatch, settings)
    fake = _patch_client(monkeypatch)
    user.stripe_customer_id = "cus_existing"
    await db.flush()

    await BillingService(db=db, settings=settings).create_checkout_session(
        user=user, plan=Plan.STUDENT, request_origin=None
    )

    [call] = fake.checkout_sessions.calls
    assert call["customer"] == "cus_existing"
    assert "customer_email" not in call


async def test_checkout_refuses_the_free_plan(
    db: AsyncSession, settings: Settings, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_billing(monkeypatch, settings)
    _patch_client(monkeypatch)

    with pytest.raises(Conflict):
        await BillingService(db=db, settings=settings).create_checkout_session(
            user=user, plan=Plan.FREE, request_origin=None
        )


async def test_checkout_fails_closed_when_billing_is_not_configured(
    db: AsyncSession, settings: Settings, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The actual state of every NOEMA deployment today: no Stripe key set."""
    monkeypatch.setattr(settings, "noema_stripe_secret_key", "")

    with pytest.raises(FeatureUnavailable):
        await BillingService(db=db, settings=settings).create_checkout_session(
            user=user, plan=Plan.PRO, request_origin=None
        )


async def test_checkout_fails_closed_when_a_plan_has_no_price_configured(
    db: AsyncSession, settings: Settings, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "noema_stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(settings, "noema_stripe_price_pro", "")

    with pytest.raises(FeatureUnavailable):
        await BillingService(db=db, settings=settings).create_checkout_session(
            user=user, plan=Plan.PRO, request_origin=None
        )


async def test_portal_requires_an_existing_stripe_customer(
    db: AsyncSession, settings: Settings, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_billing(monkeypatch, settings)
    _patch_client(monkeypatch)

    with pytest.raises(Conflict):
        await BillingService(db=db, settings=settings).create_portal_session(
            user=user, request_origin=None
        )


async def test_portal_opens_for_an_already_subscribed_user(
    db: AsyncSession, settings: Settings, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_billing(monkeypatch, settings)
    fake = _patch_client(monkeypatch)
    user.stripe_customer_id = "cus_existing"
    await db.flush()

    url = await BillingService(db=db, settings=settings).create_portal_session(
        user=user, request_origin=None
    )

    assert url == "https://billing.stripe.com/fake-portal"
    assert fake.portal_sessions.calls[0]["customer"] == "cus_existing"


async def test_webhook_rejects_a_bad_signature(
    db: AsyncSession, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_billing(monkeypatch, settings)

    def _raise(*args: Any, **kwargs: Any) -> Any:
        import stripe

        raise stripe.SignatureVerificationError(  # type: ignore[no-untyped-call]
            "bad sig", "sig_header"
        )

    monkeypatch.setattr("noema.services.billing.stripe.Webhook.construct_event", _raise)

    with pytest.raises(Conflict):
        await BillingService(db=db, settings=settings).handle_webhook(
            payload=b"{}", signature="bad"
        )


async def test_webhook_fails_closed_when_unconfigured(
    db: AsyncSession, settings: Settings
) -> None:
    with pytest.raises(FeatureUnavailable):
        await BillingService(db=db, settings=settings).handle_webhook(
            payload=b"{}", signature=None
        )


async def test_checkout_completed_sets_the_right_users_plan(
    db: AsyncSession,
    settings: Settings,
    user: User,
    other_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tenancy: the event's metadata ties back to exactly one user, never the
    other real account that happens to exist in the same database."""
    _configure_billing(monkeypatch, settings)
    event = _checkout_completed_event(event_id="evt_1", user_id=str(user.id), plan="pro")
    monkeypatch.setattr(
        "noema.services.billing.stripe.Webhook.construct_event", lambda *a, **k: event
    )

    await BillingService(db=db, settings=settings).handle_webhook(
        payload=b"{}", signature="sig"
    )
    await db.flush()

    assert user.plan == Plan.PRO
    assert user.stripe_customer_id == "cus_123"
    assert other_user.plan == Plan.FREE


async def test_a_replayed_webhook_event_is_a_no_op(
    db: AsyncSession, settings: Settings, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stripe redelivers events; the second delivery of the same event id must
    not re-apply the plan change (or anything else)."""
    _configure_billing(monkeypatch, settings)
    event = _checkout_completed_event(
        event_id="evt_dup", user_id=str(user.id), plan="max"
    )
    monkeypatch.setattr(
        "noema.services.billing.stripe.Webhook.construct_event", lambda *a, **k: event
    )
    service = BillingService(db=db, settings=settings)

    await service.handle_webhook(payload=b"{}", signature="sig")
    assert user.plan == Plan.MAX

    # A second, identical delivery -- change the plan back manually first so a
    # real re-application (the bug this test exists to catch) is observable.
    user.plan = Plan.FREE
    await db.flush()
    await service.handle_webhook(payload=b"{}", signature="sig")

    assert user.plan == Plan.FREE  # unchanged by the replay, not reset to MAX
    from sqlalchemy import func, select

    count = await db.scalar(
        select(func.count())
        .select_from(StripeEvent)
        .where(StripeEvent.event_id == "evt_dup")
    )
    assert count == 1


async def test_subscription_deleted_reverts_to_free(
    db: AsyncSession, settings: Settings, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_billing(monkeypatch, settings)
    user.plan = Plan.PRO
    await db.flush()
    event = _subscription_deleted_event(event_id="evt_cancel", user_id=str(user.id))
    monkeypatch.setattr(
        "noema.services.billing.stripe.Webhook.construct_event", lambda *a, **k: event
    )

    await BillingService(db=db, settings=settings).handle_webhook(
        payload=b"{}", signature="sig"
    )

    assert user.plan == Plan.FREE


async def test_an_unmatched_user_id_does_not_crash_the_webhook(
    db: AsyncSession, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A checkout for an account that no longer exists (deleted between
    checkout and webhook delivery) must be logged, not a 500."""
    _configure_billing(monkeypatch, settings)
    event = _checkout_completed_event(
        event_id="evt_ghost",
        user_id="00000000-0000-4000-8000-000000000000",
        plan="pro",
    )
    monkeypatch.setattr(
        "noema.services.billing.stripe.Webhook.construct_event", lambda *a, **k: event
    )

    await BillingService(db=db, settings=settings).handle_webhook(
        payload=b"{}", signature="sig"
    )  # must not raise
