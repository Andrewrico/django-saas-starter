"""Stripe interactions and webhook handling."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from .models import Plan, StripeEvent, Subscription
from .stripe_client import get_stripe

logger = logging.getLogger(__name__)
User = get_user_model()


class BillingError(Exception):
    """A user-facing billing problem (maps to HTTP 400)."""


def _subscription_for(user) -> Subscription | None:  # type: ignore[no-untyped-def]
    return Subscription.objects.filter(user=user).first()


def _ensure_customer(user, plan: Plan) -> Subscription:  # type: ignore[no-untyped-def]
    sub = _subscription_for(user)
    if sub is None:
        sub = Subscription.objects.create(user=user, plan=plan, status="incomplete")
    if not sub.stripe_customer_id:
        customer = get_stripe().Customer.create(email=user.email, metadata={"user_id": str(user.pk)})
        sub.stripe_customer_id = customer["id"]
        sub.save(update_fields=["stripe_customer_id", "updated_at"])
    return sub


def create_checkout_session(user, plan_slug: str) -> str:  # type: ignore[no-untyped-def]
    from django.conf import settings

    plan = Plan.objects.filter(slug=plan_slug, is_public=True).first()
    if plan is None or not plan.stripe_price_id:
        raise BillingError("That plan cannot be purchased.")
    sub = _ensure_customer(user, plan)
    if sub.is_active and sub.stripe_subscription_id:
        raise BillingError("You already have an active subscription; use the billing portal to change it.")
    session = get_stripe().checkout.Session.create(
        mode="subscription",
        customer=sub.stripe_customer_id,
        line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
        success_url=settings.BILLING_SUCCESS_URL,
        cancel_url=settings.BILLING_CANCEL_URL,
        client_reference_id=str(user.pk),
        metadata={"user_id": str(user.pk), "plan": plan.slug},
    )
    return session["url"]


def create_portal_session(user) -> str:  # type: ignore[no-untyped-def]
    from django.conf import settings

    sub = _subscription_for(user)
    if sub is None or not sub.stripe_customer_id:
        raise BillingError("No billing account yet.")
    session = get_stripe().billing_portal.Session.create(
        customer=sub.stripe_customer_id, return_url=settings.BILLING_PORTAL_RETURN_URL
    )
    return session["url"]


def construct_event(payload: bytes, signature: str) -> dict[str, Any]:
    """Verify the Stripe signature and parse the event. Raises ValueError if invalid."""
    from django.conf import settings

    stripe = get_stripe()
    try:
        stripe.Webhook.construct_event(payload, signature, settings.STRIPE_WEBHOOK_SECRET)
        return json.loads(payload)  # type: ignore[no-any-return]
    except (stripe.SignatureVerificationError, ValueError) as exc:
        raise ValueError("Invalid webhook signature or payload") from exc


def _period_end(obj: dict[str, Any]) -> datetime | None:
    ts = obj.get("current_period_end")
    if ts is None:  # newer API versions moved it onto the subscription items
        items = (obj.get("items") or {}).get("data") or []
        ts = items[0].get("current_period_end") if items else None
    return datetime.fromtimestamp(ts, tz=UTC) if ts else None


def _apply_subscription(obj: dict[str, Any]) -> None:
    customer_id = obj.get("customer")
    sub = Subscription.objects.filter(stripe_customer_id=customer_id).first()
    if sub is None:
        logger.warning("Webhook for unknown Stripe customer %s ignored", customer_id)
        return
    items = (obj.get("items") or {}).get("data") or []
    price_id = (items[0].get("price") or {}).get("id") if items else None
    plan = Plan.objects.filter(stripe_price_id=price_id).first() if price_id else None
    if plan is not None:
        sub.plan = plan
    sub.stripe_subscription_id = obj.get("id") or sub.stripe_subscription_id
    sub.status = obj.get("status", sub.status)
    sub.cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
    sub.current_period_end = _period_end(obj) or sub.current_period_end
    sub.save()


def _handle_checkout_completed(obj: dict[str, Any]) -> None:
    sub = Subscription.objects.filter(stripe_customer_id=obj.get("customer")).first()
    if sub is None:
        logger.warning("Checkout completed for unknown customer %s", obj.get("customer"))
        return
    if obj.get("subscription"):
        sub.stripe_subscription_id = obj["subscription"]
        sub.save(update_fields=["stripe_subscription_id", "updated_at"])


def handle_event(event: dict[str, Any]) -> bool:
    """Process an event once. Returns False when it was already processed."""
    try:
        with transaction.atomic():
            StripeEvent.objects.create(event_id=event["id"], event_type=event["type"])
            obj = event["data"]["object"]
            if event["type"] == "checkout.session.completed":
                _handle_checkout_completed(obj)
            elif event["type"] in (
                "customer.subscription.created",
                "customer.subscription.updated",
                "customer.subscription.deleted",
            ):
                _apply_subscription(obj)
            # Other event types are recorded and ignored.
    except IntegrityError:
        return False
    return True
