"""Account use-cases shared by the JSON API and the HTML pages."""

from django.conf import settings
from django.contrib.auth import authenticate
from django.db import IntegrityError, transaction
from django.http import HttpRequest

from apps.billing.limits import get_plan
from apps.core.email import send_email

from .models import User


class EmailTaken(Exception):
    """Raised when the email is already registered (case-insensitive)."""


def verification_required() -> bool:
    return settings.ACCOUNT_EMAIL_VERIFICATION == "mandatory"


def email_is_verified(user: User) -> bool:
    from allauth.account.models import EmailAddress

    return EmailAddress.objects.filter(user=user, verified=True).exists()


def register_user(request: HttpRequest, email: str, password: str, name: str = "") -> User:
    """Create a user, record an allauth email address and send mail.

    Sends the verification mail when verification is enabled, otherwise the
    welcome mail.
    """
    from allauth.account.models import EmailAddress

    email = email.strip().lower()
    if User.objects.filter(email__iexact=email).exists():
        raise EmailTaken
    try:
        with transaction.atomic():
            user = User.objects.create_user(email=email, password=password, name=name)
    except IntegrityError as exc:  # lost a race with a concurrent signup
        raise EmailTaken from exc
    address = EmailAddress.objects.create(user=user, email=email, primary=True, verified=False)
    if settings.ACCOUNT_EMAIL_VERIFICATION == "none":
        send_email(email, "Welcome", "welcome", {"email": email, "plan_name": get_plan(user).name})
    else:
        address.send_confirmation(request, signup=True)
    return user


def authenticate_user(request: HttpRequest, email: str, password: str) -> User | None:
    """Return the active user for valid credentials, honouring mandatory verification."""
    user = authenticate(request, username=email.strip().lower(), password=password)
    if user is None:
        return None
    assert isinstance(user, User)
    if verification_required() and not email_is_verified(user):
        return None
    return user
