"""Bounded content inspection. Never trust extension, MIME headers or storage paths."""

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from rest_framework.exceptions import ValidationError


def inspect_upload(file: UploadedFile) -> tuple[int, str]:
    maximum = settings.UPLOAD_MAX_FILE_BYTES
    if file.size > maximum:
        raise ValidationError({"file": f"Files must be at most {maximum} bytes."})
    data = file.read(maximum + 1)
    file.seek(0)
    if not data or len(data) > maximum:
        raise ValidationError({"file": "File is empty or exceeds the size limit."})
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        content_type = "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        content_type = "image/jpeg"
    elif data.startswith((b"GIF87a", b"GIF89a")):
        content_type = "image/gif"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        content_type = "image/webp"
    elif data.startswith(b"%PDF-"):
        content_type = "application/pdf"
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise ValidationError({"file": "Unsupported file content."}) from None
        if any(ord(char) < 32 and char not in "\t\r\n" for char in text):
            raise ValidationError({"file": "Unsupported file content."})
        content_type = "text/plain"
    return len(data), content_type
