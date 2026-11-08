"""Server-rendered pages: landing, login, signup, account settings, delete account."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.billing import services as billing
from apps.billing.limits import get_plan
from apps.billing.models import Plan, Subscription
from apps.billing.stripe_client import billing_enabled
from apps.core.email import send_email

from . import services
from .forms import DeleteAccountForm, LoginForm, ProfileForm, SignupForm


def home(request: HttpRequest) -> HttpResponse:
    """Landing page. Pricing comes from the public plans (edit them in the admin)."""
    plans = Plan.objects.filter(is_public=True)
    return render(request, "accounts/home.html", {"plans": plans, "billing_enabled": billing_enabled()})


class LoginPage(DjangoLoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):  # type: ignore[no-untyped-def]
        user = form.get_user()
        if services.verification_required() and not services.email_is_verified(user):
            form.add_error(None, "Please verify your email address before signing in.")
            return self.form_invalid(form)
        # Use allauth's login stages, including MFA, instead of Django's direct login.
        return services.begin_login(self.request, user, redirect_url=self.get_success_url())


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
    plan = get_plan(request.user)
    context: dict[str, object] = {
        "form": form,
        "plan": plan,
        "billing_enabled": billing_enabled(),
        "mfa_enrollment_enabled": settings.MFA_ENROLLMENT_ENABLED,
    }
    if billing_enabled():
        status = request.GET.get("billing")
        if status == "success":
            context["billing_notice"] = "Thanks! Your plan updates as soon as Stripe confirms the payment."
        elif status == "cancelled":
            context["billing_notice"] = "Checkout was cancelled. You have not been charged."
        sub = Subscription.objects.filter(user=request.user).first()
        has_paid_plan = sub is not None and sub.is_active and bool(sub.stripe_subscription_id)
        context["can_manage_billing"] = sub is not None and bool(sub.stripe_customer_id)
        context["upgrade_plans"] = (
            []
            if has_paid_plan
            else Plan.objects.filter(is_public=True).exclude(stripe_price_id="").exclude(pk=plan.pk)
        )
    return render(request, "accounts/settings.html", context)


@login_required
@require_http_methods(["POST"])
def billing_checkout(request: HttpRequest, slug: str) -> HttpResponse:
    """Start Stripe Checkout for a plan (POST + CSRF from the account or pricing page)."""
    if not billing_enabled():
        raise Http404
    try:
        url = billing.create_checkout_session(request.user, slug)
    except billing.BillingError as exc:
        messages.error(request, str(exc))
        return redirect("account-settings")
    return HttpResponseRedirect(url, status=303)


@login_required
@require_http_methods(["POST"])
def billing_portal(request: HttpRequest) -> HttpResponse:
    """Open the Stripe customer portal (change plan, card, invoices, cancel)."""
    if not billing_enabled():
        raise Http404
    try:
        url = billing.create_portal_session(request.user)
    except billing.BillingError as exc:
        messages.error(request, str(exc))
        return redirect("account-settings")
    return HttpResponseRedirect(url, status=303)


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
