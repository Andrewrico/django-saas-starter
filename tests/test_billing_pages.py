"""Upgrade and manage-billing buttons on the account and pricing pages (Stripe mocked)."""

from unittest import mock

import pytest
from django.test import Client, override_settings

from apps.billing.models import Plan, Subscription

pytestmark = pytest.mark.django_db

ENABLED = override_settings(
    BILLING_ENABLED=True, STRIPE_SECRET_KEY="sk_test_x", STRIPE_WEBHOOK_SECRET="whsec"
)


@pytest.fixture
def pro_plan():
    plan = Plan.objects.get(slug="pro")
    plan.stripe_price_id = "price_pro"
    plan.price_label = "$9/month"
    plan.save()
    return plan


def fake_stripe():
    fake = mock.MagicMock()
    fake.Customer.create.return_value = {"id": "cus_new"}
    fake.checkout.Session.create.return_value = {"url": "https://checkout.stripe.test/pay"}
    fake.billing_portal.Session.create.return_value = {"url": "https://billing.stripe.test/portal"}
    return mock.patch("apps.billing.services.get_stripe", return_value=fake)


def test_no_buttons_and_404_when_billing_off(client, user, pro_plan):
    client.force_login(user)
    content = client.get("/account/").content
    assert b"Upgrade to" not in content and b"Manage billing" not in content
    assert client.post("/account/billing/checkout/pro/").status_code == 404
    assert client.post("/account/billing/portal/").status_code == 404


@ENABLED
def test_free_user_sees_upgrade_and_checkout_redirects(client, user, pro_plan):
    client.force_login(user)
    content = client.get("/account/").content.decode()
    assert "Upgrade to Pro ($9/month)" in content and "Manage billing" not in content
    with fake_stripe():
        resp = client.post("/account/billing/checkout/pro/")
    assert resp.status_code == 303 and resp["Location"] == "https://checkout.stripe.test/pay"
    # Now a customer exists, so the portal button shows.
    assert "Manage billing" in client.get("/account/").content.decode()


@ENABLED
def test_paid_user_sees_portal_not_upgrade(client, user, pro_plan):
    Subscription.objects.create(
        user=user, plan=pro_plan, status="active", stripe_customer_id="cus_1", stripe_subscription_id="sub_1"
    )
    client.force_login(user)
    content = client.get("/account/").content.decode()
    assert "Upgrade to" not in content and "Manage billing" in content
    with fake_stripe():
        resp = client.post("/account/billing/portal/")
    assert resp.status_code == 303 and resp["Location"] == "https://billing.stripe.test/portal"


@ENABLED
def test_errors_come_back_as_messages(client, user, pro_plan):
    client.force_login(user)
    resp = client.post("/account/billing/checkout/free/", follow=True)
    assert b"cannot be purchased" in resp.content
    resp = client.post("/account/billing/portal/", follow=True)
    assert b"No billing account yet" in resp.content


@ENABLED
def test_checkout_needs_login_post_and_csrf(client, user, pro_plan):
    assert client.post("/account/billing/checkout/pro/").status_code == 302  # to login
    client.force_login(user)
    assert client.get("/account/billing/checkout/pro/").status_code == 405
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(user)
    assert strict.post("/account/billing/checkout/pro/").status_code == 403


@ENABLED
def test_return_notices(client, user, pro_plan):
    client.force_login(user)
    assert b"as soon as Stripe confirms" in client.get("/account/?billing=success").content
    assert b"not been charged" in client.get("/account/?billing=cancelled").content


@ENABLED
def test_pricing_card_posts_to_checkout_for_signed_in_users(client, user, pro_plan):
    assert 'href="/signup/">Choose Pro' in client.get("/").content.decode()
    client.force_login(user)
    assert 'action="/account/billing/checkout/pro/"' in client.get("/").content.decode()
