from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .models import Post


class StaticViewSitemap(Sitemap):
    changefreq = "weekly"
    priority = 1.0

    def items(self):
        return ["home", "blog-list"]

    def location(self, item: str) -> str:
        return reverse(item)


class PostSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return Post.objects.filter(status=Post.Status.PUBLISHED)

    def lastmod(self, obj: Post):
        return obj.updated_at
