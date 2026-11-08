import re

import pytest
from allauth.account.models import EmailAddress
from django.core import mail

from apps.accounts.models import User

from .conftest import PASSWORD
from .test_mfa import SECRET, reauthenticate

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def json_api(api):
    api.default_format = "json"


def test_add_verify_and_promote_email(client, user):
    EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=False)
    client.force_login(user)
    reauthenticate(client)
    assert client.get("/accounts/email/").status_code == 200
    assert client.post("/accounts/email/", {"email": "New@example.com", "action_add": ""}).status_code == 302
    new = EmailAddress.objects.get(user=user, email="new@example.com")
    assert not new.primary and not new.verified
    # Even when the original address is unverified, the new login must first be verified.
    response = client.post("/accounts/email/", {"email": new.email, "action_primary": ""}, follow=True)
    assert b"Verify your email" in response.content
    user.refresh_from_db()
    assert user.email == "alice@example.com"
    url = re.search(r"http://testserver(/accounts/confirm-email/[^\s]+/)", mail.outbox[-1].body)[1]
    assert client.get(url).status_code == 200
    assert client.post(url).status_code == 302
    new.refresh_from_db()
    assert new.verified
    client.post("/accounts/email/", {"email": new.email, "action_primary": ""})
    user.refresh_from_db()
    assert user.email == new.email
    client.post("/logout/")
    assert (
        client.post(
            "/api/auth/login/", {"email": new.email, "password": PASSWORD}, content_type="application/json"
        ).status_code
        == 200
    )


def test_cannot_take_other_users_email_or_promote_their_address(client, user, make_user):
    other = make_user(email="other@example.com")
    EmailAddress.objects.create(user=other, email=other.email, primary=True, verified=True)
    client.force_login(user)
    reauthenticate(client)
    response = client.post("/accounts/email/", {"email": "OTHER@example.com", "action_add": ""})
    assert response.status_code == 200
    assert not EmailAddress.objects.filter(user=user, email__iexact=other.email).exists()
    client.post("/accounts/email/", {"email": other.email, "action_primary": ""})
    user.refresh_from_db()
    assert user.email != other.email


def test_signup_cannot_take_reserved_secondary_address(api, client, user):
    EmailAddress.objects.create(user=user, email="reserved@example.com", primary=False)
    body = {"email": "RESERVED@example.com", "password": PASSWORD}
    assert api.post("/api/auth/signup/", body).status_code == 400
    assert client.post("/signup/", body).status_code == 200
    assert not User.objects.filter(email__iexact=body["email"]).exists()


def test_email_changes_need_login_csrf_and_reauth(user):
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    assert client.get("/accounts/email/").status_code == 302
    client.force_login(user)
    assert client.post("/accounts/email/", {"email": "new@example.com", "action_add": ""}).status_code == 403
    normal = Client()
    normal.force_login(user)
    assert normal.post("/accounts/email/", {"email": "new@example.com", "action_add": ""}).status_code == 302
    assert not EmailAddress.objects.filter(email="new@example.com").exists()


def test_mfa_user_can_add_email_after_fresh_reauthentication(client, user):
    from allauth.mfa.totp.internal.auth import TOTP

    EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
    TOTP.activate(user, SECRET)
    client.force_login(user)
    response = client.post("/accounts/email/", {"email": "new@example.com", "action_add": ""})
    assert response.status_code == 302
    assert not EmailAddress.objects.filter(email="new@example.com").exists()
    reauthenticate(client)
    assert client.post("/accounts/email/", {"email": "new@example.com", "action_add": ""}).status_code == 302
    assert EmailAddress.objects.filter(user=user, email="new@example.com", verified=False).exists()
