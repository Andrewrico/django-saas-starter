import pytest
from django.core import mail
from django.test import override_settings
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from apps.accounts.models import User

from .conftest import PASSWORD

pytestmark = pytest.mark.django_db


def signup(api, email="new@example.com", password=PASSWORD, **extra):
    return api.post("/api/auth/signup/", {"email": email, "password": password, **extra}, format="json")


def test_signup_logs_in_and_sends_verification_mail(api):
    resp = signup(api, name="Newbie")
    assert resp.status_code == 201
    assert resp.json()["plan"] == "free"
    assert "password" not in resp.json()
    assert api.get("/api/auth/me/").json()["email"] == "new@example.com"
    assert len(mail.outbox) == 1


@override_settings(ACCOUNT_EMAIL_VERIFICATION="none")
def test_signup_without_verification_sends_welcome(api):
    assert signup(api).status_code == 201
    assert mail.outbox[0].subject == "Welcome"
    assert "Free" in mail.outbox[0].body


@override_settings(ACCOUNT_EMAIL_VERIFICATION="mandatory")
def test_mandatory_verification_blocks_session_and_login(api):
    resp = signup(api)
    assert resp.status_code == 201
    assert resp.json()["verification_required"] is True
    assert api.get("/api/auth/me/").status_code == 403
    login = api.post("/api/auth/login/", {"email": "new@example.com", "password": PASSWORD}, format="json")
    assert login.status_code == 400


def test_signup_duplicate_email_is_case_insensitive(api, user):
    resp = signup(api, email="ALICE@example.com")
    assert resp.status_code == 400
    assert "email" in resp.json()


def test_signup_rejects_weak_password(api):
    assert signup(api, password="12345678").status_code == 400


def test_login_logout_me_flow(api, user):
    bad = api.post("/api/auth/login/", {"email": user.email, "password": "nope"}, format="json")
    assert bad.status_code == 400
    ok = api.post("/api/auth/login/", {"email": "Alice@Example.com", "password": PASSWORD}, format="json")
    assert ok.status_code == 200
    assert api.get("/api/auth/me/").json()["email"] == user.email
    assert api.post("/api/auth/logout/").status_code == 204
    assert api.get("/api/auth/me/").status_code == 403


def test_inactive_user_cannot_login(api, user):
    user.is_active = False
    user.save()
    resp = api.post("/api/auth/login/", {"email": user.email, "password": PASSWORD}, format="json")
    assert resp.status_code == 400


def test_me_requires_auth(api):
    assert api.get("/api/auth/me/").status_code == 403


def test_me_patch_updates_name_only(auth_api, user):
    resp = auth_api.patch("/api/auth/me/", {"name": "Alice", "email": "evil@example.com"}, format="json")
    assert resp.status_code == 200
    user.refresh_from_db()
    assert user.name == "Alice"
    assert user.email == "alice@example.com"


def test_delete_account_needs_correct_password(auth_api, user):
    assert auth_api.delete("/api/auth/me/", {"password": "wrong"}, format="json").status_code == 400
    assert User.objects.filter(pk=user.pk).exists()
    assert auth_api.delete("/api/auth/me/", {"password": PASSWORD}, format="json").status_code == 204
    assert not User.objects.filter(pk=user.pk).exists()
    assert mail.outbox[-1].subject == "Account deleted"


def test_csrf_enforced_on_unsafe_session_requests(user):
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(user)
    assert client.post("/api/auth/logout/").status_code == 403
    token = client.get("/api/auth/csrf/").json()["csrfToken"]
    assert client.post("/api/auth/logout/", HTTP_X_CSRFTOKEN=token).status_code == 204


def test_csrf_enforced_on_login(user):
    client = APIClient(enforce_csrf_checks=True)
    body = {"email": user.email, "password": PASSWORD}
    assert client.post("/api/auth/login/", body, format="json").status_code == 403
    token = client.get("/api/auth/csrf/").json()["csrfToken"]
    assert client.post("/api/auth/login/", body, format="json", HTTP_X_CSRFTOKEN=token).status_code == 200


def test_auth_endpoints_are_throttled(api, monkeypatch):
    monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, "auth", "2/min")
    body = {"email": "x@example.com", "password": "nope"}
    codes = [api.post("/api/auth/login/", body, format="json").status_code for _ in range(3)]
    assert codes == [400, 400, 429]


def test_user_manager_validation(db):
    with pytest.raises(ValueError):
        User.objects.create_user(email="")
    with pytest.raises(ValueError):
        User.objects.create_superuser(email="a@example.com", password="x", is_staff=False)
    admin = User.objects.create_superuser(email="Root@Example.com", password="x")
    assert admin.is_superuser and admin.email == "root@example.com"
    assert str(admin) == "root@example.com"
