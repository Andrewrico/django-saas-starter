"""The main user journeys in a real browser against a live server."""

import re
from unittest import mock

import pytest
from playwright.sync_api import Page, expect

from apps.accounts.models import User
from apps.billing.models import Plan

PASSWORD = "correct-horse-battery-9"


@pytest.fixture
def site(live_server):
    return live_server.url


def sign_up(page: Page, site: str, email: str = "e2e@example.com") -> None:
    page.goto(f"{site}/signup/")
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name="Sign up").click()
    expect(page).to_have_url(re.compile(r"/account/$"))


def test_landing_page_and_pricing(page: Page, site):
    page.goto(site)
    expect(page.get_by_role("heading", level=1)).to_contain_text("Ship your SaaS")
    page.get_by_role("link", name="Pricing").click()
    pricing = page.locator("#pricing")
    expect(pricing).to_contain_text("Free")
    expect(pricing).to_contain_text("Up to 20 projects")
    page.get_by_text("Do I need a credit card to start?").click()
    expect(page.get_by_text("Everyone starts on the free plan.")).to_be_visible()


@pytest.mark.parametrize("width", [390, 1280])
def test_no_horizontal_scroll_and_one_line_header(page: Page, site, width):
    page.set_viewport_size({"width": width, "height": 800})
    for path in ("/", "/login/", "/signup/"):
        page.goto(site + path)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), path
        assert page.locator(".site-header").bounding_box()["height"] < 80, path


def test_signup_logout_login_and_profile(page: Page, site):
    sign_up(page, site)
    expect(page.get_by_text("e2e@example.com")).to_be_visible()
    page.get_by_label("Name").fill("Edie")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_role("status")).to_contain_text("Profile saved")

    page.get_by_role("button", name="Sign out").click()
    page.goto(f"{site}/login/")
    page.get_by_label("Email").fill("e2e@example.com")
    page.get_by_label("Password").fill("wrong-password-123")
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_role("alert")).to_be_visible()
    page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    expect(page).to_have_url(re.compile(r"/account/$"))


def test_delete_account(page: Page, site):
    sign_up(page, site, "bye@example.com")
    page.get_by_role("link", name="Delete account").click()
    page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name=re.compile("Delete", re.I)).click()
    expect(page.get_by_role("status")).to_contain_text("deleted")
    assert not User.objects.filter(email="bye@example.com").exists()


def stop_redirect(page: Page, url_glob: str) -> dict:
    """Let our server answer, record where it redirects, and stop there (no real network)."""
    captured: dict = {}

    def handler(route):
        response = route.fetch(max_redirects=0)
        captured["status"] = response.status
        captured["location"] = response.headers.get("location", "")
        route.fulfill(status=200, body="stopped before leaving the site")

    page.route(url_glob, handler)
    return captured


def test_social_button_starts_provider_login(page: Page, site, settings):
    settings.SOCIALACCOUNT_PROVIDERS = {"github": {"APPS": [{"client_id": "cid", "secret": "s"}]}}
    captured = stop_redirect(page, "**/accounts/github/login/**")
    page.goto(f"{site}/login/")
    page.get_by_role("button", name="Continue with GitHub").click()
    expect(page.get_by_text("stopped before leaving the site")).to_be_visible()
    assert captured["status"] == 302
    assert captured["location"].startswith("https://github.com/login/oauth/authorize?")
    assert "client_id=cid" in captured["location"]


def test_upgrade_button_goes_to_stripe_checkout(page: Page, site, settings):
    settings.BILLING_ENABLED = True
    settings.STRIPE_SECRET_KEY = "sk_test_x"
    settings.STRIPE_WEBHOOK_SECRET = "w"
    # The live server's database is emptied between tests, so create the plan here.
    Plan.objects.update_or_create(
        slug="pro",
        defaults={
            "name": "Pro",
            "limits": {"max_items": 1000},
            "stripe_price_id": "price_pro",
            "price_label": "$9/month",
            "sort_order": 10,
        },
    )
    fake = mock.MagicMock()
    fake.Customer.create.return_value = {"id": "cus_e2e"}
    fake.checkout.Session.create.return_value = {"url": "https://checkout.stripe.test/c/pay"}
    sign_up(page, site, "buyer@example.com")
    captured = stop_redirect(page, "**/account/billing/checkout/**")
    with mock.patch("apps.billing.services.get_stripe", return_value=fake):
        page.get_by_role("button", name="Upgrade to Pro ($9/month)").click()
        expect(page.get_by_text("stopped before leaving the site")).to_be_visible()
    assert captured == {"status": 303, "location": "https://checkout.stripe.test/c/pay"}
    page.unroute("**/account/billing/checkout/**")
    page.goto(f"{site}/account/?billing=cancelled")
    expect(page.get_by_text("You have not been charged.")).to_be_visible()
    expect(page.get_by_role("button", name="Manage billing")).to_be_visible()
