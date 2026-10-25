"""Transactional email helper.

Renders ``templates/emails/<template>.txt`` (required) and ``<template>.html``
(optional). The backend comes from ``EMAIL_BACKEND`` (console in dev).
"""

import contextlib
from collections.abc import Sequence

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string


def send_email(to: str | Sequence[str], subject: str, template: str, context: dict | None = None) -> int:
    ctx = {"SITE_NAME": settings.SITE_NAME, **(context or {})}
    recipients = [to] if isinstance(to, str) else list(to)
    text = render_to_string(f"emails/{template}.txt", ctx)
    message = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, recipients)
    with contextlib.suppress(TemplateDoesNotExist):
        message.attach_alternative(render_to_string(f"emails/{template}.html", ctx), "text/html")
    return message.send()
