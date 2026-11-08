"""POST /internal/jobs/run/: off by default, Google OIDC or bearer-token auth, runs jobs."""

import json
import time
from unittest import mock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import override_settings

from apps.core import job_registry, job_trigger

pytestmark = pytest.mark.django_db

URL = "/internal/jobs/run/"
AUDIENCE = "https://app.example.com/internal/jobs/run/"
INVOKER = "scheduler@proj.iam.gserviceaccount.com"
OIDC_ON = {"JOBS_OIDC_AUDIENCE": AUDIENCE, "JOBS_INVOKER_EMAIL": INVOKER, "JOBS_TRIGGER_TOKEN": ""}
SHARED = "s" * 40
GOOGLE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def google_token(key=GOOGLE_KEY, **overrides):
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": AUDIENCE,
        "email": INVOKER,
        "email_verified": True,
        "iat": now,
        "exp": now + 300,
        "sub": "1234",
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256")


@pytest.fixture
def google_keys():
    """Pretend Google's published signing key is GOOGLE_KEY (no network)."""
    with mock.patch.object(job_trigger, "_signing_key", return_value=GOOGLE_KEY.public_key()):
        yield


@pytest.fixture
def clean_registry():
    saved = dict(job_registry._REGISTRY)
    yield
    job_registry._REGISTRY.clear()
    job_registry._REGISTRY.update(saved)


def post(client, token=None, body=None):
    headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
    data = json.dumps(body) if body is not None else ""
    return client.post(URL, data=data, content_type="application/json", **headers)


def test_off_by_default(client):
    assert post(client, token="anything").status_code == 404


@override_settings(**OIDC_ON)
def test_only_post(client):
    assert client.get(URL).status_code == 405


@override_settings(**OIDC_ON)
def test_google_token_runs_all_jobs(client, google_keys):
    resp = post(client, token=google_token())
    assert resp.status_code == 200
    jobs = resp.json()["jobs"]
    assert jobs["clear_expired_sessions"] == "ok" and jobs["prune_stripe_events"] == "ok"


@override_settings(**OIDC_ON)
@pytest.mark.parametrize(
    "token",
    [
        pytest.param(lambda: google_token(key=OTHER_KEY), id="forged-signature"),
        pytest.param(lambda: google_token(aud="https://other.example.com/"), id="wrong-audience"),
        pytest.param(lambda: google_token(email="intruder@proj.iam.gserviceaccount.com"), id="wrong-sa"),
        pytest.param(lambda: google_token(email_verified=False), id="unverified-email"),
        pytest.param(lambda: google_token(iss="https://evil.example.com"), id="wrong-issuer"),
        pytest.param(lambda: google_token(exp=int(time.time()) - 60), id="expired"),
        pytest.param(lambda: "not-a-jwt", id="garbage"),
    ],
)
def test_bad_google_tokens_are_rejected(client, google_keys, token):
    assert post(client, token=token()).status_code == 401


@override_settings(**OIDC_ON)
def test_missing_or_wrong_scheme(client, google_keys):
    assert post(client).status_code == 401
    resp = client.post(URL, HTTP_AUTHORIZATION=f"Basic {google_token()}")
    assert resp.status_code == 401


@override_settings(**OIDC_ON)
def test_key_fetch_failure_is_rejected_not_500(client):
    with mock.patch.object(job_trigger, "_signing_key", side_effect=jwt.PyJWKClientError("down")):
        assert post(client, token=google_token()).status_code == 401


@override_settings(JOBS_TRIGGER_TOKEN=SHARED, JOBS_OIDC_AUDIENCE="", JOBS_INVOKER_EMAIL="")
def test_shared_token(client):
    assert post(client, token=SHARED).status_code == 200
    assert post(client, token="s" * 39 + "x").status_code == 401
    # An OIDC token is useless when only the shared token is configured.
    assert post(client, token=google_token()).status_code == 401


@override_settings(JOBS_TRIGGER_TOKEN=SHARED)
def test_selected_jobs_and_validation(client, clean_registry):
    calls = []
    job_registry.job("tick")(lambda: calls.append(1))
    resp = post(client, token=SHARED, body={"jobs": ["tick"]})
    assert resp.status_code == 200 and resp.json() == {"jobs": {"tick": "ok"}} and calls == [1]
    assert post(client, token=SHARED, body={"jobs": ["nope"]}).json()["unknown"] == ["nope"]
    assert post(client, token=SHARED, body={"jobs": "tick"}).status_code == 400
    assert post(client, token=SHARED, body={"jobs": ["x" * 5000]}).status_code == 413


@override_settings(JOBS_TRIGGER_TOKEN=SHARED)
def test_failed_job_returns_500(client, clean_registry):
    @job_registry.job("boom")
    def boom():
        raise RuntimeError("x")

    resp = post(client, token=SHARED, body={"jobs": ["boom"]})
    assert resp.status_code == 500 and resp.json() == {"jobs": {"boom": "failed"}}


def test_short_shared_token_refused_at_startup(monkeypatch):
    import importlib

    from django.core.exceptions import ImproperlyConfigured

    import config.settings as settings_module

    monkeypatch.setenv("JOBS_TRIGGER_TOKEN", "short")
    try:
        with pytest.raises(ImproperlyConfigured, match="32"):
            importlib.reload(settings_module)
    finally:
        monkeypatch.undo()
        importlib.reload(settings_module)


def test_jwks_client_is_cached():
    job_trigger._google_jwks.cache_clear()
    assert job_trigger._google_jwks() is job_trigger._google_jwks()
