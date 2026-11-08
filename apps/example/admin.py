from django.contrib import admin

from .models import Attachment, Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "created_at")
    list_filter = ("created_at",)
    search_fields = ("name", "owner__email")
    raw_id_fields = ("owner",)
    date_hierarchy = "created_at"


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "project", "size", "content_type", "created_at")
    search_fields = ("original_filename", "project__owner__email")
    fields = ("project", "original_filename", "size", "content_type", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request):  # type: ignore[no-untyped-def]
        return False
