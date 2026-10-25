from django.urls import path

from . import views

urlpatterns = [
    path("plans/", views.PlanListView.as_view(), name="billing-plans"),
    path("subscription/", views.SubscriptionView.as_view(), name="billing-subscription"),
    path("checkout/", views.CheckoutView.as_view(), name="billing-checkout"),
    path("portal/", views.PortalView.as_view(), name="billing-portal"),
    path("webhook/", views.webhook, name="billing-webhook"),
]
