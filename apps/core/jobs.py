"""Jobs owned by the core app."""

from django.core.management import call_command

from .job_registry import job


@job("clear_expired_sessions")
def clear_expired_sessions() -> None:
    call_command("clearsessions")
