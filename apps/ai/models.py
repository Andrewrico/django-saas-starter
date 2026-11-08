from django.conf import settings
from django.db import models


class AIRequest(models.Model):
    """One call to the model: the usage log and the basis of the daily per-plan limit.

    The user's text and the answer are NOT stored, only sizes and outcome.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_requests")
    task = models.CharField(max_length=20)
    input_chars = models.PositiveIntegerField(default=0)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    outcome = models.CharField(max_length=20, default="pending")  # ok | refused | error | pending
    model = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "created_at"])]

    def __str__(self) -> str:
        return f"{self.user_id} {self.task} {self.outcome}"
