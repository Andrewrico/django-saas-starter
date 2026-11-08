from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.LoginPage.as_view(), name="login"),
    path("signup/", views.signup, name="signup"),
    path("logout/", views.logout_view, name="logout"),
    path("account/", views.account_settings, name="account-settings"),
    path("account/delete/", views.delete_account, name="account-delete"),
    path("account/billing/checkout/<slug:slug>/", views.billing_checkout, name="billing-checkout-page"),
    path("account/billing/portal/", views.billing_portal, name="billing-portal-page"),
]
