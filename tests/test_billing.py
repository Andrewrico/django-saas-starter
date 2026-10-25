import hashlib
import hmac
import json
import subprocess
import sys
import time
from datetime import timedelta
from unittest import mock

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.billing import jobs, services
from apps.billing.limits import get_limit, get_plan
from apps.billing.models import Plan, StripeEvent, Subscription

pytestmark = pytest.mark.django_db
SECRET = "whsec_test"

ENABLED = override_settings(BILLING_ENABLED=True, STRIPE_SECRET_KEY="sk_test_x", STRIPE_WEBHOOK_SECRET=SECRET)


def signed(payload: dict, secret: str = SECRET) -> tuple[bytes, str]:
    body = json.dumps(payload).encode()
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return body, f"t={ts},v1={sig}"


def post_webhook(api, payload, secret=SECRET, header=None):
    body, sig = signed(payload, secret)
    return api.post(
        "/api/billing/webhook/", body, content_type="application/json", HTTP_STRIPE_SIGNATURE=header or sig
    )


def sub_event(event_id="evt_1", status="active", customer="cus_1", etype="customer.subscription.updated"):
    return {
        "id": event_id,
        "object": "event",
        "type": etype,
        "data": {
            "object": {
                "id": "sub_1",
                "customer": customer,
                "status": status,
                "cancel_at_period_end": False,
                "items": {"data": [{"price": {"id": "price_pro"}, "current_period_end": 1900000000}]},
            }
        },
    }


@pytest.fixture
def pro_plan():
    plan = Plan.objects.get(slug="pro")
    plan.stripe_price_id = "price_pro"
    plan.save()
    return plan


# --- plans & defaults -------------------------------------------------------


def test_everyone_is_on_free_plan_by_default(user):
    assert get_plan(user).slug == "free"
    assert get_limit(user, "max_items") == 20
    assert get_limit(user, "missing", 7) == 7


def test_anonymous_gets_free_plan():
    from django.contrib.auth.models import AnonymousUser

    assert get_plan(AnonymousUser()).slug == "free"


def test_free_plan_is_recreated_if_missing(user):
    Plan.objects.filter(slug="free").delete()
    assert get_plan(user).limits == {"max_items": 20}


def test_active_subscription_changes_plan_but_inactive_does_not(user, pro_plan):
    sub = Subscription.objects.create(user=user, plan=pro_plan, status="active")
    assert get_plan(user).slug == "pro"
    sub.status = "canceled"
    sub.save()
    assert get_plan(user).slug == "free"
    assert str(sub) and str(pro_plan) == "Pro"


def test_plan_limit_ignores_non_integers():
    assert Plan(slug="x", name="X", limits={"max_items": "lots", "flag": True}).limit("max_items", 3) == 3
    assert Plan(slug="x", name="X", limits={"flag": True}).limit("flag") is None


def test_plans_and_subscription_endpoints(auth_api, api, pro_plan):
    plans = api.get("/api/billing/plans/").json()
    assert [p["slug"] for p in plans] == ["free", "pro"]
    sub = auth_api.get("/api/billing/subscription/").json()
    assert sub == {"plan": "free", "limits": {"max_items": 20}, "billing_enabled": False}
    assert api.get("/api/billing/subscription/").status_code == 403


# --- disabled by default ------------------------------------------------------


def test_billing_endpoints_are_404_when_disabled(auth_api, api):
    assert auth_api.post("/api/billing/checkout/", {"plan": "pro"}, format="json").status_code == 404
    assert auth_api.post("/api/billing/portal/").status_code == 404
    body, sig = signed({"id": "evt_x", "type": "x", "data": {"object": {}}})
    resp = api.post("/api/billing/webhook/", body, content_type="application/json", HTTP_STRIPE_SIGNATURE=sig)
    assert resp.status_code == 404


@override_settings(BILLING_ENABLED=True, STRIPE_SECRET_KEY="", STRIPE_WEBHOOK_SECRET="")
def test_enabled_flag_without_keys_stays_disabled(auth_api):
    assert auth_api.post("/api/billing/portal/").status_code == 404


def test_stripe_is_not_imported_when_billing_is_disabled():
    code = (
        "import os, sys, django;"
        "os.environ['DJANGO_SETTINGS_MODULE']='config.settings';"
        "django.setup();"
        "from django.test import Client;"
        "import config.urls;"
        "assert 'stripe' not in sys.modules, 'stripe was imported'"
    )
    env = {
        "DEBUG": "true",
        "SECRET_KEY": "x",
        "BILLING_ENABLED": "false",
        "DJANGO_READ_DOT_ENV_FILE": "false",
        "PATH": "",
        "DATABASE_URL": "sqlite:///:memory:",
    }
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=False
    )
    assert result.returncode == 0, result.stderr


# --- webhook ------------------------------------------------------------------


@ENABLED
def test_webhook_rejects_bad_signature(api):
    payload = sub_event()
    assert post_webhook(api, payload, secret="whsec_wrong").status_code == 400
    assert post_webhook(api, payload, header="garbage").status_code == 400
    body = b"not json"
    resp = api.post("/api/billing/webhook/", body, content_type="application/json")
    assert resp.status_code == 400
    assert StripeEvent.objects.count() == 0


@ENABLED
def test_webhook_updates_subscription_and_is_idempotent(api, user, pro_plan):
    Subscription.objects.create(user=user, plan=Plan.objects.get(slug="free"), stripe_customer_id="cus_1")
    first = post_webhook(api, sub_event())
    assert first.status_code == 200 and first.json()["duplicate"] is False
    sub = Subscription.objects.get(user=user)
    assert (sub.plan.slug, sub.status, sub.stripe_subscription_id) == ("pro", "active", "sub_1")
    assert sub.current_period_end is not None
    assert get_plan(user).slug == "pro"

    sub.status = "past_due"
    sub.save()
    again = post_webhook(api, sub_event())  # same event id
    assert again.json()["duplicate"] is True
    sub.refresh_from_db()
    assert sub.status == "past_due"  # replay did not re-apply
    assert StripeEvent.objects.filter(event_id="evt_1").count() == 1


@ENABLED
def test_webhook_subscription_deleted_returns_user_to_free(api, user, pro_plan):
    Subscription.objects.create(user=user, plan=pro_plan, stripe_customer_id="cus_1", status="active")
    event = sub_event("evt_del", status="canceled", etype="customer.subscription.deleted")
    assert post_webhook(api, event).status_code == 200
    assert get_plan(user).slug == "free"


@ENABLED
def test_webhook_legacy_period_end_and_unknown_price(api, user):
    Subscription.objects.create(user=user, plan=Plan.objects.get(slug="free"), stripe_customer_id="cus_1")
    event = sub_event("evt_legacy")
    obj = event["data"]["object"]
    obj["current_period_end"] = 1900000000
    obj["items"] = {"data": [{"price": {"id": "price_unknown"}}]}
    assert post_webhook(api, event).status_code == 200
    sub = Subscription.objects.get(user=user)
    assert sub.plan.slug == "free"  # unknown price leaves the plan untouched
    assert sub.current_period_end is not None
    obj2 = sub_event("evt_noitems")
    obj2["data"]["object"].pop("items")
    assert post_webhook(api, obj2).status_code == 200


@ENABLED
def test_webhook_checkout_completed_and_unknown_customer(api, user):
    Subscription.objects.create(user=user, plan=Plan.objects.get(slug="free"), stripe_customer_id="cus_1")
    done = {
        "id": "evt_c",
        "type": "checkout.session.completed",
        "data": {"object": {"customer": "cus_1", "subscription": "sub_9"}},
    }
    assert post_webhook(api, done).status_code == 200
    assert Subscription.objects.get(user=user).stripe_subscription_id == "sub_9"
    ghost = {
        "id": "evt_g",
        "type": "checkout.session.completed",
        "data": {"object": {"customer": "cus_zzz", "subscription": "s"}},
    }
    assert post_webhook(api, ghost).status_code == 200
    assert post_webhook(api, sub_event("evt_g2", customer="cus_zzz")).status_code == 200
    other = {"id": "evt_o", "type": "invoice.paid", "data": {"object": {}}}
    assert post_webhook(api, other).status_code == 200


# --- checkout / portal (Stripe mocked) -----------------------------------------


@ENABLED
def test_checkout_creates_customer_and_session(auth_api, user, pro_plan):
    fake = mock.MagicMock()
    fake.Customer.create.return_value = {"id": "cus_new"}
    fake.checkout.Session.create.return_value = {"url": "https://stripe.test/pay"}
    with mock.patch("apps.billing.services.get_stripe", return_value=fake):
        resp = auth_api.post("/api/billing/checkout/", {"plan": "pro"}, format="json")
    assert resp.status_code == 200 and resp.json() == {"url": "https://stripe.test/pay"}
    kwargs = fake.checkout.Session.create.call_args.kwargs
    assert kwargs["customer"] == "cus_new" and kwargs["line_items"][0]["price"] == "price_pro"
    assert kwargs["metadata"]["user_id"] == str(user.pk)
    assert Subscription.objects.get(user=user).stripe_customer_id == "cus_new"
    assert get_plan(user).slug == "free"  # not upgraded until the webhook says so


@ENABLED
def test_checkout_rejects_unpurchasable_or_duplicate(auth_api, user, pro_plan):
    assert auth_api.post("/api/billing/checkout/", {"plan": "free"}, format="json").status_code == 400
    assert auth_api.post("/api/billing/checkout/", {"plan": "nope"}, format="json").status_code == 400
    assert auth_api.post("/api/billing/checkout/", {}, format="json").status_code == 400
    Subscription.objects.create(
        user=user, plan=pro_plan, status="active", stripe_customer_id="cus_1", stripe_subscription_id="sub_1"
    )
    resp = auth_api.post("/api/billing/checkout/", {"plan": "pro"}, format="json")
    assert resp.status_code == 400 and "portal" in resp.json()["detail"]


@ENABLED
def test_portal_session(auth_api, user, pro_plan):
    assert auth_api.post("/api/billing/portal/").status_code == 400  # no billing account yet
    Subscription.objects.create(user=user, plan=pro_plan, stripe_customer_id="cus_1", status="active")
    fake = mock.MagicMock()
    fake.billing_portal.Session.create.return_value = {"url": "https://stripe.test/portal"}
    with mock.patch("apps.billing.services.get_stripe", return_value=fake):
        resp = auth_api.post("/api/billing/portal/")
    assert resp.json() == {"url": "https://stripe.test/portal"}


@ENABLED
def test_get_stripe_sets_api_key():
    from apps.billing.stripe_client import get_stripe

    assert get_stripe().api_key == "sk_test_x"


def test_get_stripe_refuses_when_disabled():
    from apps.billing.stripe_client import get_stripe

    with pytest.raises(RuntimeError):
        get_stripe()


def test_construct_event_helper_is_importable():
    assert callable(services.construct_event)


# --- jobs ---------------------------------------------------------------------


def test_prune_stripe_events_job():
    old = StripeEvent.objects.create(event_id="old", event_type="x")
    StripeEvent.objects.filter(pk=old.pk).update(
        received_at=timezone.now() - timedelta(days=jobs.RETENTION_DAYS + 1)
    )
    StripeEvent.objects.create(event_id="new", event_type="x")
    assert jobs.prune_stripe_events() == 1
    assert list(StripeEvent.objects.values_list("event_id", flat=True)) == ["new"]
