from pathlib import PureWindowsPath

from django.conf import settings
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.billing.limits import get_plan

from .models import Attachment, Project
from .uploads import inspect_upload
from .views import LimitReached


class AttachmentSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = ["id", "original_filename", "size", "content_type", "created_at", "download_url"]
        read_only_fields = fields

    def get_download_url(self, obj: Attachment) -> str:
        return reverse("attachment-download", args=[obj.project_id, obj.pk])


class UploadSerializer(serializers.Serializer):
    file = serializers.FileField(max_length=255)


class OwnerAttachmentView(APIView):
    def project(self, request, project_id: int) -> Project:  # type: ignore[no-untyped-def]
        if not settings.UPLOADS_ENABLED:
            raise Http404
        return get_object_or_404(Project, pk=project_id, owner=request.user)

    def attachment(self, request, project_id: int, pk: int) -> Attachment:  # type: ignore[no-untyped-def]
        project = self.project(request, project_id)
        return get_object_or_404(Attachment, project=project, pk=pk)


class AttachmentListView(OwnerAttachmentView):
    parser_classes = [MultiPartParser]

    @extend_schema(responses=AttachmentSerializer(many=True))
    def get(self, request, project_id: int) -> Response:  # type: ignore[no-untyped-def]
        project = self.project(request, project_id)
        return Response(AttachmentSerializer(project.attachments.all(), many=True).data)

    @extend_schema(request=UploadSerializer, responses={201: AttachmentSerializer})
    def post(self, request, project_id: int) -> Response:  # type: ignore[no-untyped-def]
        project = self.project(request, project_id)
        serializer = UploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        file = serializer.validated_data["file"]
        size, content_type = inspect_upload(file)
        filename = PureWindowsPath(file.name).name
        filename = "".join(char for char in filename if char.isprintable())[:255] or "attachment"
        attachment = Attachment(
            project=project, original_filename=filename, size=size, content_type=content_type
        )
        try:
            with transaction.atomic():
                user = User.objects.select_for_update().get(pk=request.user.pk)
                plan = get_plan(user)
                maximum = plan.limit("max_files", 10 if plan.slug == "free" else None)
                if maximum is not None and Attachment.objects.filter(project__owner=user).count() >= maximum:
                    raise LimitReached(f"Your {plan.name} plan allows at most {maximum} files.")
                attachment.file.save(file.name, file, save=False)
                attachment.save()
        except Exception:
            # Storage writes aren't transactional: undo one when the DB save fails.
            if attachment.file.name:
                attachment.file.storage.delete(attachment.file.name)
            raise
        return Response(AttachmentSerializer(attachment).data, status=201)


class AttachmentDetailView(OwnerAttachmentView):
    @extend_schema(responses={204: None})
    def delete(self, request, project_id: int, pk: int) -> Response:  # type: ignore[no-untyped-def]
        self.attachment(request, project_id, pk).delete()
        return Response(status=204)


class AttachmentDownloadView(OwnerAttachmentView):
    @extend_schema(responses={(200, "application/octet-stream"): bytes})
    def get(self, request, project_id: int, pk: int) -> FileResponse:  # type: ignore[no-untyped-def]
        attachment = self.attachment(request, project_id, pk)
        response = FileResponse(
            attachment.file.open("rb"),
            as_attachment=True,
            filename=attachment.original_filename,
            content_type=attachment.content_type,
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response
