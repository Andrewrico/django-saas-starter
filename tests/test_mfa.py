import time
from unittest.mock import patch

import pytest
from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes
from allauth.mfa.totp.internal.auth import TOTP, format_hotp_value, hotp_value
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from .conftest import PASSWORD
from .test_social import GITHUB_ON, fake_github, start_github_login

pytestmark = pytest.mark.django_db
SECRET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


@pytest.fixture(autouse=True)
def json_api(api):
    api.default_format = "json"


@pytest.fixture(autouse=True)
def fixed_totp_period():
    # Keep real HOTP/TOTP validation while avoiding a 30-second boundary mid-test.
    with patch("allauth.mfa.totp.internal.auth.time.time", return_value=int(time.time())):
        yield


@pytest.fixture
def enrolled(user):
    EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
    TOTP.activate(user, SECRET)
    codes = RecoveryCodes.activate(user).get_unused_codes()
    return user, codes


def current_code(secret=SECRET):
    return format_hotp_value(hotp_value(secret, int(time.time()) // 30))


def api_password(api, user):
    return api.post("/api/auth/login/", {"email": user.email, "password": PASSWORD}, format="json")


@pytest.mark.parametrize("url,key", [("/login/", "username"), ("/accounts/login/", "login")])
@pytest.mark.parametrize("recovery", [False, True])
def test_every_page_login_requires_second_factor(client, enrolled, url, key, recovery):
    user, codes = enrolled
    response = client.post(url, {key: user.email, "password": PASSWORD})
    assert response.status_code == 302
    assert response["Location"] == "/accounts/2fa/authenticate/"
    assert "_auth_user_id" not in client.session
    assert client.get("/account/").status_code == 302
    assert client.get(response["Location"]).status_code == 200
    bad = client.post(response["Location"], {"code": "wrong"})
    assert bad.status_code == 200
    assert "_auth_user_id" not in client.session
    code = codes[0] if recovery else current_code()
    assert client.post(response["Location"], {"code": code}).status_code == 302
    assert client.get("/account/").status_code == 200
    client.post("/logout/")
    # Clear cache to model another process/restart; replay protection must persist in the DB.
    cache.clear()
    client.post(url, {key: user.email, "password": PASSWORD})
    assert client.post("/accounts/2fa/authenticate/", {"code": code}).status_code == 200
    assert "_auth_user_id" not in client.session


@pytest.mark.parametrize("recovery", [False, True])
def test_api_mfa_challenge_and_single_use(api, enrolled, recovery):
    user, codes = enrolled
    response = api_password(api, user)
    assert response.status_code == 401 and response.json()["mfa_required"] is True
    assert api.get("/api/auth/me/").status_code == 403
    assert api.post("/api/auth/login/mfa/", {"code": "bad"}).status_code == 400
    code = codes[0] if recovery else current_code()
    good = api.post("/api/auth/login/mfa/", {"code": code})
    assert good.status_code == 200 and good.json()["email"] == user.email
    assert api.post("/api/auth/login/mfa/", {"code": code}).status_code == 400
    api.post("/api/auth/logout/")
    cache.clear()
    api_password(api, user)
    assert api.post("/api/auth/login/mfa/", {"code": code}).status_code == 400
    assert api.get("/api/auth/me/").status_code == 403


def test_mfa_challenge_is_bound_to_session_and_expires(api, enrolled, settings):
    user, codes = enrolled
    assert api.post("/api/auth/login/mfa/", {"code": codes[0]}).status_code == 400
    api_password(api, user)
    assert APIClient().post("/api/auth/login/mfa/", {"code": codes[0]}).status_code == 400
    settings.ACCOUNT_LOGIN_TIMEOUT = 1
    with patch("allauth.account.internal.stagekit.time.time", return_value=time.time() + 60):
        assert api.post("/api/auth/login/mfa/", {"code": codes[0]}).status_code == 400
    api_password(api, user)
    user.is_active = False
    user.save()
    assert api.post("/api/auth/login/mfa/", {"code": codes[0]}).status_code == 400


def test_mfa_csrf_and_throttle(enrolled, monkeypatch):
    user, codes = enrolled
    strict = APIClient(enforce_csrf_checks=True)
    strict.default_format = "json"
    token = strict.get("/api/auth/csrf/").json()["csrfToken"]
    assert (
        strict.post(
            "/api/auth/login/", {"email": user.email, "password": PASSWORD}, HTTP_X_CSRFTOKEN=token
        ).status_code
        == 401
    )
    assert strict.post("/api/auth/login/mfa/", {"code": codes[0]}).status_code == 403
    monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, "auth", "2/min")
    cache.clear()
    statuses = [
        strict.post("/api/auth/login/mfa/", {"code": "bad"}, HTTP_X_CSRFTOKEN=token).status_code
        for _ in range(3)
    ]
    assert statuses == [400, 400, 429]


def test_admin_login_routes_through_mfa(client, enrolled):
    user, codes = enrolled
    user.is_staff = True
    user.save()
    response = client.post("/admin/login/", {"username": user.email, "password": PASSWORD})
    assert response.status_code == 302 and response["Location"].startswith("/login/")
    assert "_auth_user_id" not in client.session
    response = client.post(response["Location"], {"username": user.email, "password": PASSWORD})
    assert response["Location"] == "/accounts/2fa/authenticate/"
    assert "_auth_user_id" not in client.session
    client.post(response["Location"], {"code": codes[0]})
    assert client.get("/admin/").status_code == 200


@override_settings(SOCIALACCOUNT_PROVIDERS=GITHUB_ON)
def test_linked_social_login_requires_mfa(client, enrolled):
    from allauth.socialaccount.models import SocialAccount

    user, codes = enrolled
    SocialAccount.objects.create(user=user, provider="github", uid="42")
    state = start_github_login(client)
    with fake_github(email=user.email):
        response = client.get(f"/accounts/github/login/callback/?code=abc&state={state}")
    assert response["Location"] == "/accounts/2fa/authenticate/"
    assert "_auth_user_id" not in client.session
    client.post(response["Location"], {"code": codes[0]})
    assert client.get("/account/").status_code == 200


def reauthenticate(client):
    response = client.post("/accounts/reauthenticate/", {"password": PASSWORD})
    assert response.status_code == 302


def test_enrollment_disabled_by_default(client, user, settings):
    assert settings.MFA_ENROLLMENT_ENABLED is False
    client.force_login(user)
    assert client.get("/accounts/2fa/totp/activate/").status_code == 404
    assert client.post("/accounts/2fa/totp/activate/", {"code": "123456"}).status_code == 404
    assert not Authenticator.objects.exists()


@override_settings(MFA_ENROLLMENT_ENABLED=True)
def test_enroll_totp_and_get_recovery_codes(client, user):
    EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
    client.force_login(user)
    reauthenticate(client)
    response = client.get("/accounts/2fa/totp/activate/")
    assert response.status_code == 200
    secret = response.context["form"].secret
    assert client.post("/accounts/2fa/totp/activate/", {"code": "bad"}).status_code == 200
    response = client.post("/accounts/2fa/totp/activate/", {"code": current_code(secret)})
    assert response.status_code == 302
    assert "recovery-codes" in response["Location"]
    auth = Authenticator.objects.get(user=user, type="totp")
    assert secret not in auth.data["secret"]
    assert client.get(response["Location"]).status_code == 200
    assert client.get("/accounts/2fa/").status_code == 200
    assert client.get("/accounts/2fa/totp/activate/").status_code == 302
    client.post("/logout/")
    client.post("/login/", {"username": user.email, "password": PASSWORD})
    assert client.post("/accounts/2fa/authenticate/", {"code": current_code(secret)}).status_code == 200
    assert "_auth_user_id" not in client.session


@override_settings(MFA_ENROLLMENT_ENABLED=True)
def test_enrollment_needs_verified_primary_and_reauthentication(client, user):
    client.force_login(user)
    assert client.get("/accounts/2fa/totp/activate/").status_code == 302
    reauthenticate(client)
    response = client.get("/accounts/2fa/totp/activate/")
    secret = response.context["form"].secret
    response = client.post("/accounts/2fa/totp/activate/", {"code": current_code(secret)})
    assert response.status_code == 200
    assert not Authenticator.objects.exists()


def test_enrollment_form_cannot_bypass_switch(user):
    from allauth.core import context
    from django.test import RequestFactory

    from apps.accounts.mfa import ActivateTOTPForm

    request = RequestFactory().get("/")
    request.session = {}
    with context.request_context(request):
        form = ActivateTOTPForm(user=user, data={"code": "123456"})
        assert not form.is_valid()


def test_mfa_reauthentication_and_key_rotation(client, enrolled, settings):
    from apps.accounts.mfa import MFAAdapter

    user, codes = enrolled
    client.force_login(user)
    assert client.post("/accounts/2fa/reauthenticate/", {"code": codes[0]}).status_code == 302
    assert client.get("/accounts/2fa/recovery-codes/").status_code == 200
    encrypted = MFAAdapter().encrypt("secret")
    old_key = settings.SECRET_KEY
    settings.SECRET_KEY = "new-rotation-key"
    settings.SECRET_KEY_FALLBACKS = [old_key]
    assert MFAAdapter().decrypt(encrypted) == "secret"


def test_mfa_wrong_password_does_not_start_challenge(api, enrolled):
    user, codes = enrolled
    assert api.post("/api/auth/login/", {"email": user.email, "password": "bad"}).status_code == 400
    assert api.post("/api/auth/login/mfa/", {"code": codes[0]}).status_code == 400
