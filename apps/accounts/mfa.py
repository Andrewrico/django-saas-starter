"""Small policy extensions around allauth's MFA and email management."""

import base64
import hashlib

from allauth.account.forms import AddEmailForm as AllauthAddEmailForm
from allauth.account.internal.flows.reauthentication import raise_if_reauthentication_required
from allauth.account.models import EmailAddress
from allauth.account.views import EmailView
from allauth.core import context
from allauth.core.internal.cryptokit import compare_user_code
from allauth.mfa.adapter import DefaultMFAAdapter, get_adapter
from allauth.mfa.base.forms import AuthenticateForm as AllauthAuthenticateForm
from allauth.mfa.base.forms import ReauthenticateForm as AllauthReauthenticateForm
from allauth.mfa.base.internal.flows import check_rate_limit
from allauth.mfa.totp.forms import ActivateTOTPForm as AllauthActivateTOTPForm
from allauth.mfa.totp.internal.auth import (
    format_hotp_value,
    hotp_value,
    yield_hotp_counters_from_time,
)
from allauth.mfa.totp.views import ActivateTOTPView
from allauth.mfa.utils import decrypt, is_mfa_enabled
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic.edit import FormView

from .models import User


class MFAAdapter(DefaultMFAAdapter):
    def encrypt(self, text: str) -> str:
        from cryptography.fernet import Fernet

        key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
        return Fernet(key).encrypt(text.encode()).decode()

    def decrypt(self, encrypted_text: str) -> str:
        from cryptography.fernet import Fernet, MultiFernet

        keys = [settings.SECRET_KEY, *settings.SECRET_KEY_FALLBACKS]
        ciphers = [Fernet(base64.urlsafe_b64encode(hashlib.sha256(k.encode()).digest())) for k in keys]
        return MultiFernet(ciphers).decrypt(encrypted_text.encode()).decode()


class PersistentReplayProtection:
    """Persist TOTP counters: allauth's default cache is per-process and can be evicted."""

    @transaction.atomic
    def clean_code(self):  # type: ignore[no-untyped-def]
        from allauth.mfa.models import Authenticator

        # Also serializes attempts across workers and recovery-code use.
        User.objects.select_for_update().get(pk=self.user.pk)
        totp = Authenticator.objects.filter(user=self.user, type=Authenticator.Type.TOTP).first()
        counter = None
        if totp:
            secret = decrypt(totp.data["secret"])
            for candidate in yield_hotp_counters_from_time():
                if compare_user_code(
                    actual=self.cleaned_data["code"],
                    expected=format_hotp_value(hotp_value(secret, candidate)),
                ):
                    counter = candidate
                    if candidate <= totp.data.get("last_counter", -1):
                        check_rate_limit(self.user)
                        raise get_adapter().validation_error("incorrect_code")
                    break
        code = super().clean_code()
        if totp and counter is not None and self.authenticator.type == Authenticator.Type.TOTP:
            totp.data["last_counter"] = counter
            totp.save(update_fields=["data"])
        return code


class AuthenticateForm(PersistentReplayProtection, AllauthAuthenticateForm):
    pass


class ReauthenticateForm(PersistentReplayProtection, AllauthReauthenticateForm):
    pass


class ActivateTOTPForm(AllauthActivateTOTPForm):
    def clean_code(self) -> str:
        if not settings.MFA_ENROLLMENT_ENABLED:
            raise ValidationError("Authenticator enrolment is disabled.")
        if not EmailAddress.objects.filter(user=self.user, primary=True, verified=True).exists():
            raise get_adapter().validation_error("unverified_email")
        return super().clean_code()


@method_decorator(never_cache, name="dispatch")
class EnrollTOTPView(ActivateTOTPView):
    template_name = "accounts/activate_totp.html"

    def dispatch(self, request, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not settings.MFA_ENROLLMENT_ENABLED:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):  # type: ignore[no-untyped-def]
        # Manual setup avoids requiring an optional QR imaging library.
        data = FormView.get_context_data(self, **kwargs)
        data["totp_url"] = get_adapter().build_totp_url(self.request.user, data["form"].secret)
        return data

    @transaction.atomic
    def form_valid(self, form):  # type: ignore[no-untyped-def]
        from allauth.mfa.models import Authenticator

        response = super().form_valid(form)
        authenticator = Authenticator.objects.get(user=self.request.user, type=Authenticator.Type.TOTP)
        # The enrolment proof is also a consumed code, before activation commits.
        for counter in yield_hotp_counters_from_time():
            if compare_user_code(
                actual=form.cleaned_data["code"], expected=format_hotp_value(hotp_value(form.secret, counter))
            ):
                authenticator.data["last_counter"] = counter
                authenticator.save(update_fields=["data"])
                break
        return response


def require_mfa_email_reauthentication(sender, user, **kwargs):  # type: ignore[no-untyped-def]
    if is_mfa_enabled(user):
        raise_if_reauthentication_required(context.request, app="allauth.mfa")


class VerifiedEmailView(EmailView):
    @transaction.atomic
    def _action_primary(self, request, *args, **kwargs):  # type: ignore[no-untyped-def]
        User.objects.select_for_update().get(pk=request.user.pk)
        address = self._get_email_address(request)
        if address and not address.verified:
            messages.error(request, "Verify your email address before making it primary.")
            return redirect("account_email")
        return super()._action_primary(request, *args, **kwargs)


class AddEmailForm(AllauthAddEmailForm):
    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        if (
            User.objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists()
            or EmailAddress.objects.filter(email__iexact=email).exclude(user=self.user).exists()
        ):
            raise ValidationError("This email address belongs to another account.")
        return super().clean_email()
