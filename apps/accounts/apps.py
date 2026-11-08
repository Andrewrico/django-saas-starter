from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"

    def ready(self) -> None:
        from allauth.account.signals import _add_email
        from allauth.mfa.signals import on_add_email

        from .mfa import require_mfa_email_reauthentication

        # Link confirmation remains available with MFA, guarded by fresh reauthentication.
        _add_email.disconnect(on_add_email)
        _add_email.connect(require_mfa_email_reauthentication)
