"""django-allauth adapters: fit social sign-in to the email-only ``User`` (no first/last name)."""

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialApp
from django.http import Http404


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def get_provider(self, request, provider, client_id=None):  # type: ignore[no-untyped-def]
        # Provider apps are always installed, but a provider without keys is "off": answer 404
        # instead of letting SocialApp.DoesNotExist become a 500.
        try:
            return super().get_provider(request, provider, client_id=client_id)
        except SocialApp.DoesNotExist:
            raise Http404("This sign-in provider is not configured.") from None

    def populate_user(self, request, sociallogin, data):  # type: ignore[no-untyped-def]
        user = super().populate_user(request, sociallogin, data)
        full_name = data.get("name") or " ".join(
            part for part in (data.get("first_name"), data.get("last_name")) if part
        )
        if full_name and not user.name:
            user.name = full_name[: user._meta.get_field("name").max_length]
        return user
