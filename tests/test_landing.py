import pytest
from django.test import override_settings

from apps.billing.models import Plan

pytestmark = pytest.mark.django_db


def test_landing_shows_public_plans_with_limits(client):
    content = client.get("/").content.decode()
    assert 'id="pricing"' in content
    assert "Free" in content and "$0" in content and "Up to 20 projects" in content
    assert "Pro" in content and "Up to 1,000 projects" in content
    assert "Coming soon" in content  # Pro has no Stripe price and billing is off
    assert "Start free" in content


def test_hidden_plans_are_not_listed(client):
    Plan.objects.filter(slug="pro").update(is_public=False)
    assert "Pro" not in client.get("/").content.decode()


@override_settings(BILLING_ENABLED=True, STRIPE_SECRET_KEY="sk_test_x", STRIPE_WEBHOOK_SECRET="whsec")
def test_purchasable_plan_gets_a_button_when_billing_is_on(client):
    Plan.objects.filter(slug="pro").update(stripe_price_id="price_123", price_label="$9/month")
    content = client.get("/").content.decode()
    assert "Choose Pro" in content and "$9/month" in content and "Coming soon" not in content


def test_landing_for_signed_in_user(client, user):
    client.force_login(user)
    content = client.get("/").content.decode()
    assert "Go to your account" in content
    assert "Create your free account" not in content


def test_limit_lines_labels_and_skips_non_numbers():
    plan = Plan(limits={"max_items": 5, "max_exports": 2, "beta": True, "note": "x"})
    assert plan.limit_lines() == ["Up to 5 projects", "Up to 2 max exports"]
