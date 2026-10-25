from django.contrib import admin

from .models import Plan, StripeEvent, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "stripe_price_id", "is_public", "sort_order")
    list_editable = ("sort_order", "is_public")
    search_fields = ("slug", "name", "stripe_price_id")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "status", "current_period_end", "cancel_at_period_end")
    list_filter = ("status", "plan")
    search_fields = ("user__email", "stripe_customer_id", "stripe_subscription_id")
    raw_id_fields = ("user",)


@admin.register(StripeEvent)
class StripeEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "event_type", "received_at")
    list_filter = ("event_type",)
    search_fields = ("event_id",)
    readonly_fields = ("event_id", "event_type", "received_at")
