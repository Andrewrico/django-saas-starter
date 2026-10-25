"""Server-rendered pages: home, login, signup, account settings, delete account."""

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.billing.limits import get_plan
from apps.core.email import send_email

from . import services
from .forms import DeleteAccountForm, LoginForm, ProfileForm, SignupForm


def home(request: HttpRequest) -> HttpResponse:
    return render(request, "accounts/home.html")


class LoginPage(DjangoLoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):  # type: ignore[no-untyped-def]
        user = form.get_user()
        if services.verification_required() and not services.email_is_verified(user):
            form.add_error(None, "Please verify your email address before signing in.")
            return self.form_invalid(form)
        return super().form_valid(form)


@require_http_methods(["GET", "POST"])
def signup(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("account-settings")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            user = services.register_user(request, data["email"], data["password"], data["name"])
        except services.EmailTaken:
            form.add_error("email", ValidationError("A user with this email already exists."))
        else:
            if services.verification_required():
                messages.success(request, "Check your inbox to verify your email, then sign in.")
                return redirect("login")
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect("account-settings")
    return render(request, "accounts/signup.html", {"form": form})


@require_http_methods(["POST"])
def logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect("home")


@login_required
@require_http_methods(["GET", "POST"])
def account_settings(request: HttpRequest) -> HttpResponse:
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile saved.")
        return redirect("account-settings")
    return render(request, "accounts/settings.html", {"form": form, "plan": get_plan(request.user)})


@login_required
@require_http_methods(["GET", "POST"])
def delete_account(request: HttpRequest) -> HttpResponse:
    form = DeleteAccountForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = request.user
        email = user.email
        logout(request)
        user.delete()
        send_email(email, "Account deleted", "account_deleted", {"email": email})
        messages.success(request, "Your account has been deleted.")
        return redirect("home")
    return render(request, "accounts/delete.html", {"form": form})
