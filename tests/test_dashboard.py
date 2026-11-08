from datetime import timedelta

import pytest
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.utils import timezone

from apps.accounts.models import User
from apps.billing.models import Plan, Subscription
from apps.core.dashboard import DASHBOARD_MAX_QUERIES, collect_stats
from apps.example.models import Project

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff(client, make_user):
    user = make_user(email="staff@example.com", is_staff=True)
    client.force_login(user)
    return user


def test_dashboard_requires_staff(client, user):
    assert client.get("/admin/dashboard/").status_code == 302
    client.force_login(user)
    resp = client.get("/admin/dashboard/")
    assert resp.status_code == 302
    assert "login" in resp["Location"]


def test_dashboard_renders_for_staff(staff, client, make_user):
    make_user(email="a@example.com")
    resp = client.get("/admin/dashboard/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Analytics dashboard" in body
    assert "Daily signups" in body
    assert "Users per plan" in body
    assert "<table>" in body


def test_admin_index_links_dashboard(staff, client):
    resp = client.get("/admin/")
    assert resp.status_code == 200
    assert b'href="/admin/dashboard/"' in resp.content


def test_stats_count_plans_emails_social_and_projects(make_user):
    free_user = make_user(email="free@example.com")
    paid = make_user(email="paid@example.com")
    social = make_user(email="social@example.com")
    pro = Plan.objects.get(slug="pro")
    Subscription.objects.create(user=paid, plan=pro, status="active", cancel_at_period_end=True)
    Subscription.objects.create(user=free_user, plan=pro, status="canceled")
    EmailAddress.objects.create(user=paid, email=paid.email, verified=True, primary=True)
    EmailAddress.objects.create(user=free_user, email=free_user.email, verified=False, primary=True)
    SocialAccount.objects.create(user=social, provider="github", uid="42")
    Project.objects.create(owner=paid, name="Recent")
    Project.objects.create(
        owner=paid,
        name="Old",
        created_at=timezone.now() - timedelta(days=40),
    )
    # force old timestamp past auto_now_add
    Project.objects.filter(name="Old").update(created_at=timezone.now() - timedelta(days=40))

    stats = collect_stats()
    by_slug = {row["slug"]: row["count"] for row in stats["users_per_plan"]}
    assert by_slug["pro"] == 1
    assert by_slug["free"] >= 2
    assert stats["active_subscriptions"] == 1
    assert stats["cancel_at_period_end"] == 1
    assert stats["emails_verified"] == 1
    assert stats["emails_unverified"] == 1
    assert stats["users_social"] == 1
    assert stats["users_password_only"] >= 2
    assert stats["projects_last_30"] == 1
    assert len(stats["daily_signups"]) == 30


def test_dashboard_query_budget(django_assert_max_num_queries, make_user):
    users = User.objects.bulk_create([User(email=f"u{i}@example.com", password="!") for i in range(40)])
    pro = Plan.objects.get(slug="pro")
    for i, user in enumerate(users[:10]):
        Subscription.objects.create(
            user=user,
            plan=pro,
            status="active" if i % 2 == 0 else "incomplete",
            cancel_at_period_end=i == 0,
        )
        EmailAddress.objects.create(user=user, email=user.email, verified=i % 2 == 0, primary=True)
    for user in users[:5]:
        SocialAccount.objects.create(user=user, provider="google", uid=f"g-{user.pk}")
        Project.objects.create(owner=user, name=f"p-{user.pk}")

    with django_assert_max_num_queries(DASHBOARD_MAX_QUERIES):
        collect_stats()


def test_plausible_off_by_default(client):
    resp = client.get("/")
    assert b"plausible.io" not in resp.content
    assert "plausible.io" not in resp["Content-Security-Policy"]


def test_plausible_script_and_csp_when_configured(client, settings):
    settings.PLAUSIBLE_DOMAIN = "example.com"
    settings.CONTENT_SECURITY_POLICY = (
        "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; "
        "script-src 'self' https://plausible.io; "
        "connect-src 'self' https://plausible.io"
    )
    resp = client.get("/")
    assert b'data-domain="example.com"' in resp.content
    assert b"https://plausible.io/js/script.js" in resp.content
    assert "plausible.io" in resp["Content-Security-Policy"]


def test_plausible_domain_amends_csp_at_import():
    from tests.test_core import run_settings

    off = run_settings({"SECRET_KEY": "k" * 60}, "'plausible.io' in s.CONTENT_SECURITY_POLICY")
    on = run_settings(
        {"SECRET_KEY": "k" * 60, "PLAUSIBLE_DOMAIN": "example.com"},
        "(s.PLAUSIBLE_DOMAIN, 'plausible.io' in s.CONTENT_SECURITY_POLICY)",
    )
    assert off.stdout.strip() == "False"
    assert on.stdout.strip() == "('example.com', True)"
