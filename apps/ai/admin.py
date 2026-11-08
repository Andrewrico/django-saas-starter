from django.contrib import admin

from .models import AIRequest


@admin.register(AIRequest)
class AIRequestAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "task", "outcome", "input_tokens", "output_tokens", "model")
    list_filter = ("task", "outcome", "model")
    search_fields = ("user__email",)
    raw_id_fields = ("user",)
    readonly_fields = [f.name for f in AIRequest._meta.fields]
