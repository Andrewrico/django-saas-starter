"""The only place Stripe is imported, and only when billing is really enabled."""

from types import ModuleType

from django.conf import settings


def billing_enabled() -> bool:
    """True only when BILLING_ENABLED is on and both Stripe secrets are set."""
    return bool(settings.BILLING_ENABLED and settings.STRIPE_SECRET_KEY and settings.STRIPE_WEBHOOK_SECRET)


def get_stripe() -> ModuleType:
    if not billing_enabled():
        raise RuntimeError("Billing is disabled")
    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe
