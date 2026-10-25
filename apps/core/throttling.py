"""Throttles shared across apps."""

from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView


class AuthRateThrottle(SimpleRateThrottle):
    """Strict limit for credential endpoints (rate key ``auth`` in settings).

    Keyed by client IP so credential stuffing from one source is slowed down
    whether or not a session exists.
    """

    scope = "auth"

    def get_cache_key(self, request: Request, view: APIView) -> str:
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}
