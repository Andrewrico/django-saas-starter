import uuid

from django.conf import settings
from django.db import models


class Project(models.Model):
    """Example owner-scoped resource. Copy this pattern for your own models."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="projects")
    name = models.CharField(max_length=120)
    description = models.TextField(max_length=2000, blank=True)
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["owner", "-created_at"])]

    def __str__(self) -> str:
        return self.name


def attachment_path(instance: "Attachment", filename: str) -> str:
    return f"attachments/{uuid.uuid4().hex}"


class Attachment(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=attachment_path)
    original_filename = models.CharField(max_length=255)
    size = models.PositiveBigIntegerField()
    content_type = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.original_filename
