"""Small security-header middleware (complements Django's SecurityMiddleware)."""

from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse


class SecurityHeadersMiddleware:
    """Adds Content-Security-Policy and Permissions-Policy headers."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        policy = getattr(settings, "CONTENT_SECURITY_POLICY", "")
        exempt = tuple(getattr(settings, "CSP_EXEMPT_PREFIXES", ()))
        if policy and not request.path.startswith(exempt) and "Content-Security-Policy" not in response:
            response["Content-Security-Policy"] = policy
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response
