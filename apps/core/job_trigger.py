"""HTTP trigger for scheduled jobs: ``POST /internal/jobs/run/``.

For hosts where a cron process can't run next to the app (Cloud Run scales to zero; with SQLite
a separate job container would be a second writer). A scheduler calls this endpoint and the jobs
run inside the web service. It is OFF (404) unless one of these is configured:

- Google Cloud Scheduler: ``JOBS_OIDC_AUDIENCE`` + ``JOBS_INVOKER_EMAIL``. The request must carry
  a Google-signed OIDC token for that audience, issued to that service account.
- Any other scheduler (cron + curl, GitHub Actions, ...): ``JOBS_TRIGGER_TOKEN``, sent as
  ``Authorization: Bearer <token>``.
"""

import hmac
import json
import logging
from functools import lru_cache

import jwt
from django.conf import settings
from django.http import Http404, HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .job_registry import registered_jobs, run_job

logger = logging.getLogger(__name__)

GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
MAX_BODY_BYTES = 4096


@lru_cache(maxsize=1)
def _google_jwks() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(GOOGLE_CERTS_URL, cache_keys=True, lifespan=3600, timeout=5)


def _signing_key(token: str):  # type: ignore[no-untyped-def]
    return _google_jwks().get_signing_key_from_jwt(token).key


def _oidc_enabled() -> bool:
    return bool(settings.JOBS_OIDC_AUDIENCE and settings.JOBS_INVOKER_EMAIL)


def trigger_enabled() -> bool:
    return _oidc_enabled() or bool(settings.JOBS_TRIGGER_TOKEN)


def _valid_google_token(token: str) -> bool:
    try:
        claims = jwt.decode(
            token,
            _signing_key(token),
            algorithms=["RS256"],
            audience=settings.JOBS_OIDC_AUDIENCE,
            issuer=GOOGLE_ISSUERS,
            options={"require": ["exp", "iat", "iss", "aud", "email"]},
        )
    except Exception as exc:  # bad signature, expired, wrong audience, key fetch failed, ...
        logger.warning("Job trigger: rejected OIDC token (%s)", type(exc).__name__)
        return False
    return claims.get("email") == settings.JOBS_INVOKER_EMAIL and claims.get("email_verified") is True


def _authorized(request: HttpRequest) -> bool:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return False
    if settings.JOBS_TRIGGER_TOKEN and hmac.compare_digest(
        token.encode(), settings.JOBS_TRIGGER_TOKEN.encode()
    ):
        return True
    return _oidc_enabled() and _valid_google_token(token)


@csrf_exempt  # machine-to-machine; authenticated by the bearer token, not a session
@never_cache
@require_POST
def run_jobs(request: HttpRequest) -> JsonResponse:
    """Run all registered jobs, or ``{"jobs": ["name", ...]}``. 200 if all succeed, else 500."""
    if not trigger_enabled():
        raise Http404
    if not _authorized(request):
        return JsonResponse({"detail": "Unauthorized"}, status=401)

    jobs = registered_jobs()
    names = sorted(jobs)
    if request.body:
        if len(request.body) > MAX_BODY_BYTES:
            return JsonResponse({"detail": "Body too large"}, status=413)
        try:
            payload = json.loads(request.body)
            requested = payload.get("jobs") if isinstance(payload, dict) else None
        except ValueError:
            requested = None
        if requested is not None:
            if not isinstance(requested, list) or not all(isinstance(n, str) for n in requested):
                return JsonResponse({"detail": 'Expected {"jobs": ["name", ...]}'}, status=400)
            unknown = sorted(set(requested) - set(jobs))
            if unknown:
                return JsonResponse({"detail": "Unknown jobs", "unknown": unknown}, status=400)
            names = requested

    results = {name: ("ok" if run_job(name) else "failed") for name in names}
    failed = [name for name, result in results.items() if result == "failed"]
    return JsonResponse({"jobs": results}, status=500 if failed else 200)
