from __future__ import annotations

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags


class Post(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, max_length=200)
    summary = models.TextField(blank=True)
    body = models.TextField(help_text="Markdown source.")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="blog_posts",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    meta_description = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-published_at", "-id"]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        if self.status == self.Status.PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("blog-detail", kwargs={"slug": self.slug})

    @property
    def is_published(self) -> bool:
        return self.status == self.Status.PUBLISHED

    def rendered_body(self) -> str:
        from apps.blog.markdown import render_markdown

        return render_markdown(self.body)

    def plain_summary(self) -> str:
        text = self.summary or strip_tags(self.rendered_body())
        return " ".join(text.split())
