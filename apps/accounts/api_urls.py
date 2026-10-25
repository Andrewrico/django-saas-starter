from django.urls import path

from . import api_views

urlpatterns = [
    path("csrf/", api_views.CsrfView.as_view(), name="api-csrf"),
    path("signup/", api_views.SignupView.as_view(), name="api-signup"),
    path("login/", api_views.LoginView.as_view(), name="api-login"),
    path("logout/", api_views.LogoutView.as_view(), name="api-logout"),
    path("me/", api_views.MeView.as_view(), name="api-me"),
]
