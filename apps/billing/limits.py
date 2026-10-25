"""Plan lookup used by every limit check.

``get_plan(user)`` is the one function the rest of the app should call. With
billing disabled (the default) it always returns the free plan.
"""

from .models import Plan, Subscription

FREE_DEFAULT_LIMITS = {"max_items": 20}


def get_free_plan() -> Plan:
    plan, _ = Plan.objects.get_or_create(
        slug=Plan.FREE_SLUG,
        defaults={"name": "Free", "limits": dict(FREE_DEFAULT_LIMITS), "sort_order": 0},
    )
    return plan


def get_plan(user) -> Plan:  # type: ignore[no-untyped-def]
    """Return the user's effective plan (free unless an active subscription exists)."""
    if getattr(user, "pk", None) is not None:
        sub = Subscription.objects.select_related("plan").filter(user=user).first()
        if sub is not None and sub.is_active:
            return sub.plan
    return get_free_plan()


def get_limit(user, key: str, default: int | None = None) -> int | None:  # type: ignore[no-untyped-def]
    return get_plan(user).limit(key, default)
