from django.conf import settings
from django.db import models


class Plan(models.Model):
    """A subscription tier. ``limits`` is free-form JSON, e.g. ``{"max_items": 20}``."""

    FREE_SLUG = "free"

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=80)
    limits = models.JSONField(default=dict, blank=True)
    stripe_price_id = models.CharField(
        max_length=120, blank=True, help_text="Stripe Price id; empty = not purchasable"
    )
    is_public = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "slug"]

    def __str__(self) -> str:
        return self.name

    def limit(self, key: str, default: int | None = None) -> int | None:
        value = self.limits.get(key, default)
        return value if isinstance(value, int) and not isinstance(value, bool) else default


class Subscription(models.Model):
    """One billing relationship per user. Only created once billing is used."""

    ACTIVE_STATUSES = ("active", "trialing")

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscription"
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    stripe_customer_id = models.CharField(max_length=120, blank=True, db_index=True)
    stripe_subscription_id = models.CharField(max_length=120, null=True, blank=True, unique=True)
    status = models.CharField(max_length=30, default="incomplete")
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.user_id}: {self.plan_id} ({self.status})"

    @property
    def is_active(self) -> bool:
        return self.status in self.ACTIVE_STATUSES


class StripeEvent(models.Model):
    """Processed webhook event ids, for idempotent handling."""

    event_id = models.CharField(max_length=120, unique=True)
    event_type = models.CharField(max_length=120)
    received_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.event_id
