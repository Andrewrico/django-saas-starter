from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import override_settings
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.billing.models import Plan, Subscription
from apps.example.models import Attachment, Project
from apps.example.uploads import inspect_upload

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def local_storage(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture
def project(user):
    return Project.objects.create(owner=user, name="Files")


def upload(client, project, data=b"hello", name="file.txt", content_type="text/plain", **extra):
    return client.post(
        f"/api/projects/{project.pk}/attachments/",
        {"file": SimpleUploadedFile(name, data, content_type=content_type), **extra},
        format="multipart",
    )


def test_uploads_off_by_default(auth_api, project, settings):
    assert settings.UPLOADS_ENABLED is False
    assert upload(auth_api, project).status_code == 404
    assert auth_api.get(f"/api/projects/{project.pk}/attachments/").status_code == 404
    assert not Attachment.objects.exists()


@override_settings(UPLOADS_ENABLED=True)
@pytest.mark.parametrize(
    "data,mime",
    [
        (b"\x89PNG\r\n\x1a\nexample", "image/png"),
        (b"\xff\xd8\xffexample", "image/jpeg"),
        (b"GIF87aexample", "image/gif"),
        (b"GIF89aexample", "image/gif"),
        (b"RIFF\x04\x00\x00\x00WEBPexample", "image/webp"),
        (b"%PDF-1.7\nexample", "application/pdf"),
        ("hello\tworld\r\n中文".encode(), "text/plain"),
    ],
)
def test_upload_sniffs_content_and_downloads_privately(auth_api, project, data, mime):
    response = upload(
        auth_api, project, data, "../../private.exe", "application/x-msdownload", owner=999, size=1
    )
    assert response.status_code == 201, response.data
    body = response.json()
    assert body["content_type"] == mime and body["size"] == len(data)
    assert body["original_filename"] == "private.exe"
    assert "file" not in body and "owner" not in body
    attachment = Attachment.objects.get(pk=body["id"])
    assert attachment.file.name.startswith("attachments/")
    assert "private" not in attachment.file.name
    assert len(attachment.file.name.split("/")[-1]) == 32
    assert str(attachment) == "private.exe"
    listing = auth_api.get(f"/api/projects/{project.pk}/attachments/").json()
    assert listing == [body]
    download = auth_api.get(body["download_url"])
    assert download["Content-Type"] == mime
    assert download["X-Content-Type-Options"] == "nosniff"
    assert download["Content-Disposition"].startswith("attachment;")
    assert download["Cache-Control"] == "private, no-store"
    assert b"".join(download.streaming_content) == data
    assert auth_api.get(f"/media/{attachment.file.name}").status_code == 404


@override_settings(UPLOADS_ENABLED=True)
def test_all_operations_are_owner_scoped(auth_api, api, project, make_user):
    response = upload(auth_api, project)
    detail = f"/api/projects/{project.pk}/attachments/{response.json()['id']}/"
    download = response.json()["download_url"]
    assert upload(api, project).status_code == 403
    assert api.get(download).status_code == 403
    api.force_login(make_user(email="other@example.com"))
    assert upload(api, project).status_code == 404
    assert api.get(f"/api/projects/{project.pk}/attachments/").status_code == 404
    assert api.get(download).status_code == 404
    assert api.delete(detail).status_code == 404
    own = Project.objects.create(owner=project.owner, name="Other")
    assert (
        auth_api.get(f"/api/projects/{own.pk}/attachments/{response.json()['id']}/download/").status_code
        == 404
    )
    assert auth_api.get(f"/api/projects/{project.pk}/attachments/999/download/").status_code == 404


@override_settings(UPLOADS_ENABLED=True, UPLOAD_MAX_FILE_BYTES=8)
def test_size_empty_and_binary_abuse(auth_api, project):
    for data in (b"123456789", b"\x00fake", b"\xffinvalid", b""):
        assert upload(auth_api, project, data, "allowed.png", "image/png").status_code == 400
    assert upload(auth_api, project, b"12345678").status_code == 201
    assert (
        auth_api.post(f"/api/projects/{project.pk}/attachments/", {}, format="multipart").status_code == 400
    )
    assert auth_api.post(f"/api/projects/{project.pk}/attachments/", {}, format="json").status_code == 415
    forged = SimpleUploadedFile("file.txt", b"x" * 9)
    forged.size = 1
    with pytest.raises(ValidationError):
        inspect_upload(forged)


@override_settings(UPLOADS_ENABLED=True)
def test_default_free_file_limit_is_across_projects(auth_api, user, project):
    free = Plan.objects.get(slug="free")
    free.limits = {"max_items": 20}  # pre-existing installations lack max_files
    free.save()
    second = Project.objects.create(owner=user, name="Second")
    for _ in range(10):
        assert upload(auth_api, project).status_code == 201
    response = upload(auth_api, second)
    assert response.status_code == 409 and "10 files" in response.json()["detail"]


@override_settings(UPLOADS_ENABLED=True)
def test_custom_plan_file_limit_and_unlimited(auth_api, user, project):
    plan = Plan.objects.create(slug="files", name="Files", limits={"max_files": 1})
    Subscription.objects.create(user=user, plan=plan, status="active")
    assert upload(auth_api, project).status_code == 201
    assert upload(auth_api, project).status_code == 409
    plan.limits = {}
    plan.save()
    assert upload(auth_api, project).status_code == 201


@override_settings(UPLOADS_ENABLED=True)
def test_upload_and_delete_need_csrf(user, project):
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(user)
    assert upload(client, project).status_code == 403
    token = client.get("/api/auth/csrf/").json()["csrfToken"]
    response = client.post(
        f"/api/projects/{project.pk}/attachments/",
        {"file": SimpleUploadedFile("f.txt", b"hello")},
        format="multipart",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 201
    assert (
        client.delete(f"/api/projects/{project.pk}/attachments/{response.json()['id']}/").status_code == 403
    )


@override_settings(UPLOADS_ENABLED=True)
@pytest.mark.parametrize("target", ["attachment", "project", "account"])
def test_delete_cascades_remove_stored_files(
    auth_api, user, project, target, django_capture_on_commit_callbacks
):
    response = upload(auth_api, project)
    attachment = Attachment.objects.get()
    storage, name = attachment.file.storage, attachment.file.name
    assert storage.exists(name)
    with django_capture_on_commit_callbacks(execute=True):
        if target == "attachment":
            assert (
                auth_api.delete(
                    f"/api/projects/{project.pk}/attachments/{response.json()['id']}/"
                ).status_code
                == 204
            )
        elif target == "project":
            assert auth_api.delete(f"/api/projects/{project.pk}/").status_code == 204
        else:
            user.delete()
    assert not storage.exists(name)
    assert not Attachment.objects.exists()


@override_settings(UPLOADS_ENABLED=True)
def test_rollback_keeps_file_and_failed_creation_removes_file(
    auth_api, project, settings, django_capture_on_commit_callbacks
):
    upload(auth_api, project)
    attachment = Attachment.objects.get()
    storage, name = attachment.file.storage, attachment.file.name
    with django_capture_on_commit_callbacks(execute=True), pytest.raises(ValueError), transaction.atomic():
        attachment.delete()
        raise ValueError("rollback")
    assert storage.exists(name)
    with (
        patch.object(Attachment, "save", side_effect=IntegrityError("database failed")),
        pytest.raises(IntegrityError),
    ):
        upload(auth_api, project)
    assert len(list(settings.MEDIA_ROOT.glob("attachments/*"))) == 1


def test_gcs_settings_are_private_and_env_driven(monkeypatch):
    import importlib

    import config.settings as module

    try:
        monkeypatch.setenv("GS_BUCKET_NAME", "private-files")
        monkeypatch.setenv("UPLOAD_MAX_FILE_BYTES", "1024")
        monkeypatch.setenv("UPLOADS_ENABLED", "true")
        monkeypatch.setenv("MFA_ENROLLMENT_ENABLED", "true")
        settings = importlib.reload(module)
        assert settings.UPLOADS_ENABLED and settings.MFA_ENROLLMENT_ENABLED
        assert settings.UPLOAD_MAX_FILE_BYTES == 1024
        assert settings.STORAGES["default"]["OPTIONS"] == {
            "bucket_name": "private-files",
            "default_acl": None,
            "querystring_auth": True,
            "file_overwrite": False,
        }
    finally:
        monkeypatch.undo()
        importlib.reload(module)
