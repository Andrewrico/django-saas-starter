import pytest
from django.contrib.auth.models import AnonymousUser  # noqa: F401
from django.core import mail
from django.test import Client, override_settings

from apps.accounts.models import User

from .conftest import PASSWORD

pytestmark = pytest.mark.django_db


def test_public_pages_render(client):
    for url in ("/", "/login/", "/signup/", "/accounts/password/reset/"):
        resp = client.get(url)
        assert resp.status_code == 200, url
        assert b"<main" in resp.content


def test_account_pages_require_login(client):
    for url in ("/account/", "/account/delete/"):
        resp = client.get(url)
        assert resp.status_code == 302
        assert resp["Location"].startswith("/login/")


def test_signup_page_creates_user_and_logs_in(client):
    resp = client.post("/signup/", {"email": "Page@Example.com", "password": PASSWORD, "name": "P"})
    assert resp.status_code == 302
    assert User.objects.get(email="page@example.com").name == "P"
    assert client.get("/account/").status_code == 200


def test_signup_page_errors(client, user):
    dup = client.post("/signup/", {"email": user.email, "password": PASSWORD})
    assert dup.status_code == 200 and b"already exists" in dup.content
    weak = client.post("/signup/", {"email": "w@example.com", "password": "12345678"})
    assert weak.status_code == 200 and not User.objects.filter(email="w@example.com").exists()


def test_signup_page_redirects_when_authenticated(client, user):
    client.force_login(user)
    assert client.get("/signup/").status_code == 302


@override_settings(ACCOUNT_EMAIL_VERIFICATION="mandatory")
def test_signup_page_with_mandatory_verification(client):
    resp = client.post("/signup/", {"email": "m@example.com", "password": PASSWORD}, follow=True)
    assert b"verify your email" in resp.content
    assert "_auth_user_id" not in client.session
    blocked = client.post("/login/", {"username": "m@example.com", "password": PASSWORD})
    assert blocked.status_code == 200 and b"verify your email" in blocked.content


def test_login_and_logout_pages(client, user):
    assert client.post("/login/", {"username": user.email, "password": "bad"}).status_code == 200
    resp = client.post("/login/", {"username": user.email, "password": PASSWORD})
    assert resp.status_code == 302
    page = client.get("/account/")
    assert user.email.encode() in page.content and b"Free" in page.content
    assert client.post("/logout/").status_code == 302
    assert client.get("/account/").status_code == 302


def test_login_page_enforces_csrf(user):
    strict = Client(enforce_csrf_checks=True)
    assert strict.post("/login/", {"username": user.email, "password": PASSWORD}).status_code == 403


def test_settings_updates_profile(client, user):
    client.force_login(user)
    resp = client.post("/account/", {"name": "Alice A"}, follow=True)
    assert b"Profile saved" in resp.content
    user.refresh_from_db()
    assert user.name == "Alice A"


def test_delete_account_page(client, user):
    client.force_login(user)
    assert client.post("/account/delete/", {"password": "wrong"}).status_code == 200
    assert User.objects.filter(pk=user.pk).exists()
    resp = client.post("/account/delete/", {"password": PASSWORD})
    assert resp.status_code == 302
    assert not User.objects.filter(pk=user.pk).exists()
    assert mail.outbox[-1].subject == "Account deleted"


def test_logout_requires_post(client):
    assert client.get("/logout/").status_code == 405


def test_admin_changelists_load(client, make_user):
    admin = User.objects.create_superuser(email="root@example.com", password=PASSWORD)
    client.force_login(admin)
    for model in (
        "accounts/user",
        "billing/plan",
        "billing/subscription",
        "billing/stripeevent",
        "example/project",
    ):
        resp = client.get(f"/admin/{model}/")
        assert resp.status_code == 200, model
        assert client.get(f"/admin/{model}/?q=test").status_code == 200
