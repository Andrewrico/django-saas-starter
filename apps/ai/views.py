"""AI assistant demo page: a signed-in user picks a task and sends some text."""

from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.billing.limits import get_limit

from .client import TASKS, AIUnavailable, ai_enabled, run_task
from .models import AIRequest

DEFAULT_DAILY_LIMIT = 10


class AIForm(forms.Form):
    task = forms.ChoiceField(choices=[(key, label) for key, (label, _) in TASKS.items()])
    text = forms.CharField(widget=forms.Textarea(attrs={"rows": 8}), strip=True)

    def clean_text(self) -> str:
        text: str = self.cleaned_data["text"]
        if len(text) > settings.AI_MAX_INPUT_CHARS:
            raise forms.ValidationError(f"Please keep it under {settings.AI_MAX_INPUT_CHARS:,} characters.")
        return text


def daily_limit(user) -> int:  # type: ignore[no-untyped-def]
    limit = get_limit(user, "ai_requests_per_day", DEFAULT_DAILY_LIMIT)
    return DEFAULT_DAILY_LIMIT if limit is None else limit


def used_today(user) -> int:  # type: ignore[no-untyped-def]
    since = timezone.now() - timedelta(days=1)
    return AIRequest.objects.filter(user=user, created_at__gte=since).count()


@login_required
@require_http_methods(["GET", "POST"])
def assistant(request: HttpRequest) -> HttpResponse:
    if not ai_enabled():
        raise Http404
    form = AIForm(request.POST or None)
    limit = daily_limit(request.user)
    context: dict[str, object] = {"form": form, "limit": limit}
    if request.method == "POST" and form.is_valid():
        if used_today(request.user) >= limit:
            context["error"] = f"You have used your {limit} requests for the last 24 hours."
        else:
            data = form.cleaned_data
            log = AIRequest.objects.create(
                user=request.user, task=data["task"], input_chars=len(data["text"])
            )
            try:
                result = run_task(data["task"], data["text"])
            except AIUnavailable as exc:
                log.outcome = "error"
                context["error"] = str(exc)
            else:
                log.outcome = "refused" if result.refused else "ok"
                log.model, log.input_tokens, log.output_tokens = (
                    result.model,
                    result.input_tokens,
                    result.output_tokens,
                )
                if result.refused:
                    context["error"] = "The assistant can't help with that request."
                else:
                    context["answer"] = result.text
            log.save()
    context["remaining"] = max(limit - used_today(request.user), 0)
    return render(request, "ai/assistant.html", context)
