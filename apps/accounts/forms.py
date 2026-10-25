from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password

from .models import User


class LoginForm(AuthenticationForm):
    username = forms.EmailField(
        label="Email", widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True})
    )


class SignupForm(forms.Form):
    email = forms.EmailField(max_length=254, widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    name = forms.CharField(max_length=150, required=False, label="Name (optional)")
    password = forms.CharField(
        max_length=128, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}), label="Password"
    )

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def clean(self) -> dict:
        cleaned = super().clean() or {}
        if cleaned.get("password") and cleaned.get("email"):
            validate_password(cleaned["password"], User(email=cleaned["email"], name=cleaned.get("name", "")))
        return cleaned


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["name"]


class DeleteAccountForm(forms.Form):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}), label="Confirm your password"
    )

    def __init__(self, user: User, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_password(self) -> str:
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("Incorrect password.")
        return password
