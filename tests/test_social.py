"""Social sign-in (Google / GitHub via django-allauth). Off unless a provider's keys are set."""

from unittest import mock
from urllib.parse import parse_qs, urlparse

import pytest
from django.test import override_settings

from apps.accounts.models import User

pytestmark = pytest.mark.django_db

GITHUB_ON = {"github": {"SCOPE": ["read:user", "user:email"], "APPS": [{"client_id": "cid", "secret": "s"}]}}


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = ""
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def fake_github(email="octo@example.com", verified=True, name="Octo Cat"):
    def request(self, method, url, *args, **kwargs):
        if url.endswith("/login/oauth/access_token"):
            return FakeResponse({"access_token": "tok", "token_type": "bearer"})
        if url.endswith("/user/emails"):
            return FakeResponse([{"email": email, "primary": True, "verified": verified}])
        if url.endswith("/user"):
            return FakeResponse({"id": 42, "login": "octo", "name": name, "email": None})
        raise AssertionError(f"unexpected request {method} {url}")

    return mock.patch("requests.Session.request", request)


def start_github_login(client):
    resp = client.post("/accounts/github/login/?process=login")
    assert resp.status_code == 302
    location = urlparse(resp["Location"])
    assert location.netloc == "github.com"
    return parse_qs(location.query)["state"][0]


def test_no_buttons_and_404_when_unconfigured(client):
    for url in ("/login/", "/signup/"):
        assert b"Continue with" not in client.get(url).content
    assert client.post("/accounts/google/login/").status_code == 404
    assert client.post("/accounts/github/login/").status_code == 404


@override_settings(SOCIALACCOUNT_PROVIDERS=GITHUB_ON)
def test_buttons_show_for_configured_provider_only(client):
    for url in ("/login/", "/signup/"):
        content = client.get(url).content
        assert b"Continue with GitHub" in content
        assert b"Continue with Google" not in content


@override_settings(SOCIALACCOUNT_PROVIDERS=GITHUB_ON)
def test_login_must_start_with_post(client):
    # A GET shows allauth's confirm page instead of redirecting (no login-by-link / CSRF).
    resp = client.get("/accounts/github/login/")
    assert resp.status_code == 200
    assert "github.com" not in resp.get("Location", "")


@override_settings(SOCIALACCOUNT_PROVIDERS=GITHUB_ON)
def test_github_signup_creates_user_with_name(client):
    state = start_github_login(client)
    with fake_github():
        resp = client.get(f"/accounts/github/login/callback/?code=abc&state={state}")
    assert resp.status_code == 302, resp.content[:500]
    user = User.objects.get(email="octo@example.com")
    assert user.name == "Octo Cat"
    assert not user.has_usable_password()
    assert client.get("/account/").status_code == 200


@override_settings(SOCIALACCOUNT_PROVIDERS=GITHUB_ON)
def test_github_does_not_take_over_existing_password_account(client, user):
    state = start_github_login(client)
    with fake_github(email=user.email):
        client.get(f"/accounts/github/login/callback/?code=abc&state={state}")
    # Not signed in as the existing user, and no second account for that email.
    assert client.session.get("_auth_user_id") != str(user.pk)
    assert User.objects.filter(email=user.email).count() == 1


@override_settings(SOCIALACCOUNT_PROVIDERS=GITHUB_ON)
def test_callback_rejects_bad_state(client):
    start_github_login(client)
    with fake_github():
        client.get("/accounts/github/login/callback/?code=abc&state=forged")
    assert not User.objects.filter(email="octo@example.com").exists()


def test_social_settings_are_read_from_env(monkeypatch):
    import importlib

    import config.settings as settings_module

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "gid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "gsecret")
    monkeypatch.delenv("GITHUB_CLIENT_ID", raising=False)
    try:
        reloaded = importlib.reload(settings_module)
        assert set(reloaded.SOCIALACCOUNT_PROVIDERS) == {"google"}
        assert reloaded.SOCIALACCOUNT_PROVIDERS["google"]["APPS"][0]["client_id"] == "gid"
    finally:
        monkeypatch.undo()
        importlib.reload(settings_module)
