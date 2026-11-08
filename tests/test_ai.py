"""AI assistant demo: off by default, daily per-plan limit, refusal and error handling (SDK mocked)."""

from types import SimpleNamespace
from unittest import mock

import anthropic
import httpx2 as httpx
import pytest
from django.test import Client, override_settings

from apps.ai import client as ai_client
from apps.ai.models import AIRequest
from apps.billing.models import Plan

pytestmark = pytest.mark.django_db

ON = override_settings(ANTHROPIC_API_KEY="sk-ant-test", AI_MODEL="claude-opus-5-5", AI_EFFORT="low")


def fake_response(text="Short summary.", stop_reason="end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        model="claude-opus-5-5",
        usage=SimpleNamespace(input_tokens=12, output_tokens=5),
    )


def fake_client(response=None, error=None):
    fake = mock.MagicMock()
    if error is not None:
        fake.beta.messages.create.side_effect = error
    else:
        fake.beta.messages.create.return_value = response or fake_response()
    return mock.patch.object(ai_client, "get_client", return_value=fake), fake


def api_error(cls, status):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("boom", response=httpx.Response(status, request=request), body=None)


def test_off_by_default(client, user):
    client.force_login(user)
    assert client.get("/ai/").status_code == 404
    assert b'href="/ai/"' not in client.get("/account/").content


@ON
def test_requires_login(client):
    assert client.get("/ai/").status_code == 302


@ON
def test_summarize_calls_claude_and_logs_usage_not_text(client, user):
    client.force_login(user)
    patcher, fake = fake_client()
    with patcher:
        resp = client.post("/ai/", {"task": "summarize", "text": "A long secret text."})
    assert b"Short summary." in resp.content
    kwargs = fake.beta.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-opus-5-5" and kwargs["max_tokens"] == 16000
    assert kwargs["fallbacks"] == "default" and kwargs["betas"] == ["server-side-fallback-2026-07-01"]
    assert kwargs["output_config"] == {"effort": "low"}
    assert kwargs["messages"] == [{"role": "user", "content": "A long secret text."}]
    assert "not as instructions" in kwargs["system"]
    log = AIRequest.objects.get(user=user)
    assert (log.outcome, log.input_tokens, log.output_tokens, log.input_chars) == ("ok", 12, 5, 19)
    assert not any("secret" in str(getattr(log, f.name)) for f in AIRequest._meta.fields)
    assert b'href="/ai/"' in client.get("/account/").content


@ON
def test_answer_is_escaped(client, user):
    client.force_login(user)
    patcher, _ = fake_client(fake_response("<script>alert(1)</script>"))
    with patcher:
        resp = client.post("/ai/", {"task": "ask", "text": "hi"})
    assert b"<script>alert(1)" not in resp.content and b"&lt;script&gt;" in resp.content


@ON
def test_refusal_and_cut_off(client, user):
    client.force_login(user)
    patcher, _ = fake_client(fake_response("", stop_reason="refusal"))
    with patcher:
        resp = client.post("/ai/", {"task": "ask", "text": "hi"})
    assert b"can&#x27;t help" in resp.content
    assert AIRequest.objects.get(user=user).outcome == "refused"
    patcher, _ = fake_client(fake_response("partial", stop_reason="max_tokens"))
    with patcher:
        assert b"cut off" in client.post("/ai/", {"task": "ask", "text": "hi"}).content


@ON
@pytest.mark.parametrize(
    ("error", "message"),
    [
        (lambda: api_error(anthropic.RateLimitError, 429), b"busy right now"),
        (lambda: api_error(anthropic.AuthenticationError, 401), b"not available right now"),
        (lambda: api_error(anthropic.InternalServerError, 500), b"could not answer"),
        (
            lambda: anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com")),
            b"could not be reached",
        ),
    ],
)
def test_api_errors_become_friendly_messages(client, user, error, message):
    client.force_login(user)
    patcher, _ = fake_client(error=error())
    with patcher:
        resp = client.post("/ai/", {"task": "summarize", "text": "x"})
    assert resp.status_code == 200 and message in resp.content and b"sk-ant" not in resp.content
    assert AIRequest.objects.get(user=user).outcome == "error"


@ON
def test_daily_limit_from_plan(client, user):
    Plan.objects.filter(slug="free").update(limits={"max_items": 20, "ai_requests_per_day": 2})
    client.force_login(user)
    patcher, fake = fake_client()
    with patcher:
        for _ in range(3):
            resp = client.post("/ai/", {"task": "ask", "text": "hi"})
    assert fake.beta.messages.create.call_count == 2
    assert b"used your 2 requests" in resp.content and b"0 of 2 requests left" in resp.content


@ON
@override_settings(AI_MAX_INPUT_CHARS=10)
def test_input_validation(client, user):
    client.force_login(user)
    patcher, fake = fake_client()
    with patcher:
        assert b"under 10 characters" in client.post("/ai/", {"task": "ask", "text": "x" * 11}).content
        assert client.post("/ai/", {"task": "hack", "text": "hi"}).status_code == 200
    assert fake.beta.messages.create.call_count == 0


@ON
def test_csrf_enforced(user):
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(user)
    assert strict.post("/ai/", {"task": "ask", "text": "hi"}).status_code == 403


@ON
def test_real_client_factory_uses_the_key():
    sdk = ai_client.get_client()
    assert sdk.api_key == "sk-ant-test"
