from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.LoginPage.as_view(), name="login"),
    path("signup/", views.signup, name="signup"),
    path("logout/", views.logout_view, name="logout"),
    path("account/", views.account_settings, name="account-settings"),
    path("account/delete/", views.delete_account, name="account-delete"),
]
