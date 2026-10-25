import os
import subprocess
import sys
from io import StringIO
from pathlib import Path
from unittest import mock

import pytest
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError
from django.test import override_settings

from apps.core import job_registry
from apps.core.email import send_email

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.django_db
def test_healthz_ok(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200 and resp.json() == {"status": "ok"}
    assert "no-cache" in resp["Cache-Control"]


def test_healthz_reports_503_when_database_is_down(client):
    with mock.patch("apps.core.views.connection.cursor", side_effect=OperationalError("down")):
        assert client.get("/healthz").status_code == 503


def test_healthz_rejects_post(client):
    assert client.post("/healthz").status_code == 405


@pytest.mark.django_db
def test_security_headers_present(client):
    resp = client.get("/")
    assert resp["Content-Security-Policy"].startswith("default-src 'self'")
    assert "camera=()" in resp["Permissions-Policy"]
    assert resp["X-Content-Type-Options"] == "nosniff"
    assert resp["X-Frame-Options"] == "DENY"
    assert resp["Referrer-Policy"] == "same-origin"


@pytest.mark.django_db
def test_csp_skipped_for_swagger_ui(client):
    resp = client.get("/api/docs/")
    assert resp.status_code == 200
    assert "Content-Security-Policy" not in resp


@pytest.mark.django_db
def test_openapi_schema_lists_api_paths(client):
    resp = client.get("/api/schema/?format=json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    for expected in ("/api/auth/signup/", "/api/auth/login/", "/api/projects/", "/api/billing/plans/"):
        assert expected in paths
    assert "/api/billing/webhook/" not in paths


def test_send_email_text_and_html(settings, tmp_path):
    (tmp_path / "emails").mkdir()
    (tmp_path / "emails" / "demo.txt").write_text("Hi {{ who }} from {{ SITE_NAME }}")
    (tmp_path / "emails" / "demo.html").write_text("<p>Hi {{ who }}</p>")
    templates = [{**settings.TEMPLATES[0], "DIRS": [tmp_path, *settings.TEMPLATES[0]["DIRS"]]}]
    with override_settings(TEMPLATES=templates):
        assert send_email(["a@example.com"], "Demo", "demo", {"who": "Ann"}) == 1
    message = mail.outbox[0]
    assert message.to == ["a@example.com"] and "Hi Ann" in message.body
    assert message.alternatives[0][1] == "text/html"


@pytest.mark.django_db
def test_send_email_without_html_template():
    send_email("a@example.com", "Bye", "account_deleted", {"email": "a@example.com"})
    assert mail.outbox[0].alternatives == []


# --- jobs -----------------------------------------------------------------------


@pytest.fixture
def clean_registry():
    saved = dict(job_registry._REGISTRY)
    yield
    job_registry._REGISTRY.clear()
    job_registry._REGISTRY.update(saved)


def test_runjobs_lists_and_runs_all(db):
    out = StringIO()
    call_command("runjobs", "--list", stdout=out)
    assert {"clear_expired_sessions", "prune_stripe_events"} <= set(out.getvalue().split())
    call_command("runjobs")
    call_command("runjobs", "prune_stripe_events")


def test_runjobs_unknown_job():
    with pytest.raises(CommandError, match="Unknown"):
        call_command("runjobs", "nope")


def test_runjobs_reports_failure(clean_registry):
    @job_registry.job("boom")
    def boom():
        raise RuntimeError("x")

    with pytest.raises(CommandError, match="boom"):
        call_command("runjobs", "boom")


def test_runjobs_loop_repeats(clean_registry):
    calls = []
    job_registry.job("tick")(lambda: calls.append(1))
    with (
        mock.patch("apps.core.management.commands.runjobs.time.sleep", side_effect=[None, KeyboardInterrupt]),
        pytest.raises(KeyboardInterrupt),
    ):
        call_command("runjobs", "tick", "--loop", "--interval", "1")
    assert len(calls) == 2


def test_duplicate_job_name_rejected(clean_registry):
    job_registry.job("dup")(lambda: None)
    with pytest.raises(ValueError):
        job_registry.job("dup")(lambda: None)


# --- settings ---------------------------------------------------------------------


def run_settings(extra_env: dict[str, str], expr: str) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "DJANGO_READ_DOT_ENV_FILE": "false",
        "DATABASE_URL": "sqlite:///:memory:",
        **extra_env,
    }
    code = f"import django.conf; from config import settings as s; print({expr})"
    return subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=ROOT, check=False
    )


def test_secure_defaults_when_debug_is_off(tmp_path):
    expr = "(s.SECURE_SSL_REDIRECT, s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, s.SECURE_HSTS_SECONDS > 0, s.BILLING_ENABLED, s.DEBUG)"
    result = run_settings({"SECRET_KEY": "k" * 60}, expr)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "(True, True, True, True, False, False)"


def test_secret_key_is_required_in_production():
    result = run_settings({}, "1")
    assert result.returncode != 0
    assert "SECRET_KEY" in result.stderr


def test_debug_mode_relaxes_https_settings():
    result = run_settings({"DEBUG": "true"}, "(s.SECURE_SSL_REDIRECT, s.SESSION_COOKIE_SECURE)")
    assert result.stdout.strip() == "(False, False)"


def test_proxy_ssl_header_is_opt_in():
    off = run_settings({"SECRET_KEY": "k" * 60}, "hasattr(s, 'SECURE_PROXY_SSL_HEADER')")
    on = run_settings({"SECRET_KEY": "k" * 60, "TRUST_PROXY_SSL_HEADER": "true"}, "s.SECURE_PROXY_SSL_HEADER")
    assert off.stdout.strip() == "False"
    assert "X_FORWARDED_PROTO" in on.stdout
