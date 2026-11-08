"""Staff-only analytics dashboard (aggregate queries only)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.db.models import Count, Exists, OuterRef, Q
from django.db.models.functions import TruncDate
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.billing.models import Plan, Subscription
from apps.example.models import Project

# Fixed query budget for the dashboard page (see tests).
DASHBOARD_MAX_QUERIES = 12


@dataclass(frozen=True)
class DailySignup:
    day: date
    count: int
    height_pct: float


def _day_start(days_ago: int = 0):
    now = timezone.localtime(timezone.now())
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start - timedelta(days=days_ago)


def collect_stats() -> dict[str, Any]:
    """Return dashboard metrics using a small, fixed set of aggregate queries."""
    User = get_user_model()
    now = timezone.now()
    today = _day_start(0)
    week = _day_start(6)  # inclusive 7 calendar days ending today
    month = _day_start(29)  # inclusive 30 calendar days
    tz = timezone.get_current_timezone()

    user_stats = User.objects.aggregate(
        total=Count("id"),
        today=Count("id", filter=Q(date_joined__gte=today)),
        last_7=Count("id", filter=Q(date_joined__gte=week)),
        last_30=Count("id", filter=Q(date_joined__gte=month)),
    )

    raw_daily = {
        row["day"]: row["count"]
        for row in (
            User.objects.filter(date_joined__gte=month)
            .annotate(day=TruncDate("date_joined", tzinfo=tz))
            .values("day")
            .annotate(count=Count("id"))
        )
        if row["day"] is not None
    }
    days: list[DailySignup] = []
    max_count = max(raw_daily.values(), default=0)
    for offset in range(29, -1, -1):
        day = (today - timedelta(days=offset)).date()
        count = raw_daily.get(day, 0)
        height = (count / max_count * 100.0) if max_count else 0.0
        days.append(DailySignup(day=day, count=count, height_pct=height))

    active_q = Q(status__in=Subscription.ACTIVE_STATUSES)
    plan_rows = list(
        Subscription.objects.filter(active_q)
        .values("plan__slug", "plan__name")
        .annotate(count=Count("id"))
        .order_by("plan__slug")
    )
    paid_total = sum(row["count"] for row in plan_rows)
    free_count = max(user_stats["total"] - paid_total, 0)
    users_per_plan = [
        {"slug": Plan.FREE_SLUG, "name": "Free", "count": free_count},
        *[{"slug": row["plan__slug"], "name": row["plan__name"], "count": row["count"]} for row in plan_rows],
    ]

    sub_stats = Subscription.objects.filter(active_q).aggregate(
        active=Count("id"),
        cancel_at_period_end=Count("id", filter=Q(cancel_at_period_end=True)),
    )

    email_stats = EmailAddress.objects.aggregate(
        n_verified=Count("id", filter=Q(verified=True)),
        n_unverified=Count("id", filter=Q(verified=False)),
    )

    has_social = Exists(SocialAccount.objects.filter(user_id=OuterRef("pk")))
    auth_stats = User.objects.annotate(_has_social=has_social).aggregate(
        n_social=Count("id", filter=Q(_has_social=True)),
        n_password_only=Count("id", filter=Q(_has_social=False)),
    )

    projects_last_30 = Project.objects.filter(created_at__gte=month).count()

    return {
        "total_users": user_stats["total"],
        "signups_today": user_stats["today"],
        "signups_last_7": user_stats["last_7"],
        "signups_last_30": user_stats["last_30"],
        "daily_signups": days,
        "users_per_plan": users_per_plan,
        "active_subscriptions": sub_stats["active"],
        "cancel_at_period_end": sub_stats["cancel_at_period_end"],
        "emails_verified": email_stats["n_verified"],
        "emails_unverified": email_stats["n_unverified"],
        "users_social": auth_stats["n_social"],
        "users_password_only": auth_stats["n_password_only"],
        "projects_last_30": projects_last_30,
        "generated_at": now,
    }


@staff_member_required
@require_GET
def staff_dashboard(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "admin/staff_dashboard.html",
        {"title": "Analytics dashboard", **collect_stats()},
    )
