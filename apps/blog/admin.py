from django.contrib import admin

from .models import Post


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "status", "author", "published_at", "updated_at")
    list_filter = ("status", "published_at")
    search_fields = ("title", "slug", "summary", "body", "meta_description")
    prepopulated_fields = {"slug": ("title",)}
    raw_id_fields = ("author",)
    date_hierarchy = "published_at"
    readonly_fields = ("updated_at",)
