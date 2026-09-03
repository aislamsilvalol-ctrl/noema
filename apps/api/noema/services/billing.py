"""Stripe checkout, the customer portal, and idempotent webhook processing.

Checkout and the portal are both Stripe's own hosted pages -- no card data ever
reaches this backend (`noema.services.billing` never sees a card number, only a
Checkout Session URL to redirect the browser to).

Entitlements stay backend-authoritative: nothing here ever writes `User.plan`
from a frontend redirect. Only `handle_webhook`, triggered by a verified Stripe
event, ever writes that column -- the same guarantee the product spec asks for
("a fonte da verdade deve ser backend + Stripe").

Every route in `noema.api.v1.billing` fails closed with `FeatureUnavailable`
when `NOEMA_STRIPE_SECRET_KEY` is unset, which is the actual state of every
NOEMA deployment until an operator configures real Stripe credentials -- there
is no fallback behavior that pretends billing works when it does not.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noema.core.config import Settings
from noema.core.errors import Conflict, FeatureUnavailable
from noema.core.logging import get_logger
from noema.db.models import Plan, StripeEvent, User

log = get_logger(__name__)

#: One Stripe Price ID per paid plan. Free has no Price -- there is nothing to
#: check out for a plan that costs nothing.
_PRICE_SETTINGS: dict[Plan, str] = {
    Plan.STUDENT: "noema_stripe_price_student",
    Plan.PRO: "noema_stripe_price_pro",
    Plan.MAX: "noema_stripe_price_max",
}

#: The subset of a subscription's status Stripe reports that should keep a user
#: on their paid plan. Anything else (canceled, incomplete_expired, unpaid) is
#: treated the same as no subscription at all -- see `_on_subscription_updated`.
_ACTIVE_SUBSCRIPTION_STATUSES = frozenset({"active", "trialing", "past_due"})


def _client(settings: Settings) -> stripe.StripeClient:
    if not settings.noema_stripe_secret_key:
        raise FeatureUnavailable(
            "Billing is not configured on this deployment. "
            "Set NOEMA_STRIPE_SECRET_KEY to enable it."
        )
    return stripe.StripeClient(settings.noema_stripe_secret_key)


@dataclass(frozen=True, slots=True)
class BillingService:
    db: AsyncSession
    settings: Settings

    async def create_checkout_session(
        self, *, user: User, plan: Plan, request_origin: str | None
    ) -> str:
        """Returns the Checkout Session URL to redirect the browser to.

        Reuses the user's existing Stripe customer if one already exists
        (`stripe_customer_id`, set the first time any checkout for this user
        ever completed) so a second subscription attempt does not fragment
        one learner's billing history across two Stripe customer records.
        """
        if plan is Plan.FREE:
            raise Conflict("The free plan has no checkout -- it costs nothing.")
        if user.plan is not Plan.FREE:
            # A second Checkout Session for an already-subscribed user creates
            # a second, separately-billed Stripe Subscription on the same
            # customer -- Stripe does not merge or replace by itself. Changing
            # an existing subscription's plan has to go through the one
            # Subscription object Stripe already tracks, which is exactly what
            # the Customer Portal does (`create_portal_session`); Checkout is
            # only for a customer's first subscription.
            raise Conflict(
                "You already have an active plan. Use the customer portal "
                "to switch plans -- starting a new checkout would create a "
                "second subscription instead of changing this one."
            )
        price_id = getattr(self.settings, _PRICE_SETTINGS.get(plan, ""), "")
        if not price_id:
            raise FeatureUnavailable(
                f"No Stripe price is configured for the {plan.value} plan yet."
            )

        client = _client(self.settings)
        origin = self.settings.web_origin(request_origin)
        session = await client.v1.checkout.sessions.create_async(
            {
                "mode": "subscription",
                "line_items": [{"price": price_id, "quantity": 1}],
                "success_url": f"{origin}/billing/success",
                "cancel_url": f"{origin}/billing",
                # Both set: client_reference_id is Stripe's own dedicated field
                # for "which of my users is this," metadata is what actually
                # survives onto the Subscription object the webhook reads for
                # subscription.updated/deleted events (client_reference_id
                # only appears on the Checkout Session itself).
                "client_reference_id": str(user.id),
                # The target plan is written here explicitly rather than
                # derived later from line items -- a Checkout Session's own
                # webhook payload does not reliably include expanded line
                # items, so metadata set at creation time is the one thing
                # guaranteed present on `checkout.session.completed`.
                "metadata": {"noema_user_id": str(user.id), "noema_plan": plan.value},
                "subscription_data": {
                    "metadata": {"noema_user_id": str(user.id), "noema_plan": plan.value}
                },
                **(
                    {"customer": user.stripe_customer_id}
                    if user.stripe_customer_id
                    else {"customer_email": user.email}
                ),
            }
        )
        if not session.url:
            raise FeatureUnavailable("Stripe did not return a checkout URL.")
        return session.url

    async def cancel_active_subscriptions(self, *, user: User) -> None:
        """Cancel every active Stripe subscription for this user, if any.

        Called from account deletion (`noema.services.account.request_deletion`
        via the `/me` route) so leaving NOEMA also stops the bill -- without
        this, a subscriber who deletes their account keeps being charged
        indefinitely, since nothing else in this codebase ever cancels a
        subscription and the account row itself is not purged for
        `GRACE_DAYS` (and Stripe has no idea NOEMA data was even deleted).

        Deliberately does not raise: deletion is a right the account holder
        is exercising right now, and it must not be blocked by billing being
        unconfigured, the user never having subscribed, or a transient Stripe
        API error -- the same "must not stop the [operation]" resilience
        already established for `purge_expired_accounts`' storage cleanup.
        """
        if not self.settings.noema_stripe_secret_key or not user.stripe_customer_id:
            return
        try:
            client = _client(self.settings)
            subscriptions = await client.v1.subscriptions.list_async(
                {"customer": user.stripe_customer_id, "status": "active"}
            )
            for subscription in subscriptions.data:
                await client.v1.subscriptions.cancel_async(subscription.id)
        except Exception as exc:  # every Stripe SDK error means the same thing here:
            # deletion must proceed regardless, an operator sees it in the logs
            log.warning(
                "stripe.subscription_cancel_failed",
                user_id=str(user.id),
                error=str(exc),
            )

    async def create_portal_session(
        self, *, user: User, request_origin: str | None
    ) -> str:
        if not user.stripe_customer_id:
            raise Conflict("No billing account exists for this user yet.")
        client = _client(self.settings)
        origin = self.settings.web_origin(request_origin)
        session = await client.v1.billing_portal.sessions.create_async(
            {
                "customer": user.stripe_customer_id,
                "return_url": f"{origin}/settings",
            }
        )
        return session.url

    async def handle_webhook(self, *, payload: bytes, signature: str | None) -> None:
        if not self.settings.noema_stripe_webhook_secret:
            raise FeatureUnavailable("Stripe webhooks are not configured.")
        try:
            event = stripe.Webhook.construct_event(
                payload, signature, self.settings.noema_stripe_webhook_secret
            )
        except (ValueError, stripe.SignatureVerificationError) as exc:
            raise Conflict("Invalid Stripe webhook signature.") from exc

        if await self._already_processed(event["id"]):
            log.info("stripe.webhook.duplicate", event_id=event["id"])
            return

        handler = _HANDLERS.get(event["type"])
        if handler is not None:
            # `construct_event` returns a typed Stripe resource for
            # `data.object` (e.g. a `checkout.Session`), not a plain dict --
            # every handler below is written against `dict.get(...)`, which
            # a Stripe SDK object deliberately does not support (it raises a
            # pointed `AttributeError` telling you to convert first, rather
            # than silently doing the wrong thing). Converting once, here, at
            # the single dispatch point, keeps every handler's existing,
            # already-correct `.get()`-based logic honest about the type it
            # actually receives.
            obj = event["data"]["object"]
            await handler(self, obj.to_dict() if hasattr(obj, "to_dict") else obj)

        self.db.add(StripeEvent(event_id=event["id"], event_type=event["type"]))
        await self.db.flush()
        log.info("stripe.webhook.processed", event_id=event["id"], type=event["type"])

    async def _already_processed(self, event_id: str) -> bool:
        existing = await self.db.scalar(
            select(StripeEvent.id).where(StripeEvent.event_id == event_id)
        )
        return existing is not None

    async def _user_for(self, noema_user_id: str | None) -> User | None:
        if not noema_user_id:
            return None
        try:
            user_id = uuid.UUID(noema_user_id)
        except ValueError:
            return None
        return await self.db.get(User, user_id)

    async def _on_checkout_completed(self, obj: dict[str, Any]) -> None:
        metadata = obj.get("metadata") or {}
        user = await self._user_for(
            obj.get("client_reference_id") or metadata.get("noema_user_id")
        )
        if user is None:
            log.warning(
                "stripe.webhook.unmatched_user",
                stripe_event="checkout.session.completed",
            )
            return
        customer_id = obj.get("customer")
        if customer_id:
            user.stripe_customer_id = customer_id
        # The plan was written into metadata at checkout-creation time
        # (`create_checkout_session`) -- reading it back here is reliable in a
        # way that re-deriving it from this event's line items is not (Stripe
        # does not guarantee expanded line items on a Checkout Session
        # webhook payload).
        try:
            plan = Plan(metadata["noema_plan"])
        except (KeyError, ValueError):
            log.warning("stripe.webhook.unknown_plan", metadata=metadata)
        else:
            user.plan = plan
        await self.db.flush()

    async def _on_subscription_updated(self, obj: dict[str, Any]) -> None:
        user = await self._user_for(obj.get("metadata", {}).get("noema_user_id"))
        if user is None:
            log.warning(
                "stripe.webhook.unmatched_user",
                stripe_event="customer.subscription.updated",
            )
            return
        if obj.get("status") not in _ACTIVE_SUBSCRIPTION_STATUSES:
            user.plan = Plan.FREE
        else:
            plan = self._plan_for_price(obj)
            if plan is not None:
                user.plan = plan
            else:
                # An active subscription whose price doesn't match any
                # configured plan (a misconfigured NOEMA_STRIPE_PRICE_* var, or
                # a price added in Stripe's dashboard nobody mapped here yet)
                # -- silently leaving the user's plan wherever it was is the
                # safe direction to fail in, but it must not be a *quiet*
                # failure the way `_on_checkout_completed`'s sibling case
                # already logs.
                log.warning(
                    "stripe.webhook.unmatched_price",
                    stripe_event="customer.subscription.updated",
                    user_id=str(user.id),
                )
        await self.db.flush()

    async def _on_subscription_deleted(self, obj: dict[str, Any]) -> None:
        user = await self._user_for(obj.get("metadata", {}).get("noema_user_id"))
        if user is None:
            log.warning(
                "stripe.webhook.unmatched_user",
                stripe_event="customer.subscription.deleted",
            )
            return
        user.plan = Plan.FREE
        await self.db.flush()

    async def _on_payment_failed(self, obj: dict[str, Any]) -> None:
        # A full dunning flow (retry emails, a grace period before downgrade)
        # is real, separate product scope this phase does not attempt --
        # logged clearly so an operator can see it happened, not silently
        # dropped.
        log.warning(
            "stripe.invoice.payment_failed",
            customer=obj.get("customer"),
            invoice=obj.get("id"),
        )

    def _plan_for_price(self, obj: dict[str, Any]) -> Plan | None:
        # A Subscription object's base payload always includes `items.data`,
        # unlike a Checkout Session's line items -- reliable to read here.
        items = (obj.get("items") or {}).get("data") or []
        price_ids = {item["price"]["id"] for item in items if item.get("price")}
        for plan, setting_name in _PRICE_SETTINGS.items():
            if getattr(self.settings, setting_name, "") in price_ids:
                return plan
        return None


_HANDLERS = {
    "checkout.session.completed": BillingService._on_checkout_completed,
    "customer.subscription.updated": BillingService._on_subscription_updated,
    "customer.subscription.deleted": BillingService._on_subscription_deleted,
    "invoice.payment_failed": BillingService._on_payment_failed,
}
