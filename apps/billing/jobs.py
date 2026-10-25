from datetime import timedelta

from django.utils import timezone

from apps.core.job_registry import job

from .models import StripeEvent

RETENTION_DAYS = 90


@job("prune_stripe_events")
def prune_stripe_events() -> int:
    """Delete webhook idempotency rows older than the retention window."""
    cutoff = timezone.now() - timedelta(days=RETENTION_DAYS)
    deleted, _ = StripeEvent.objects.filter(received_at__lt=cutoff).delete()
    return deleted
