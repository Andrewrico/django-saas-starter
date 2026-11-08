# Private project attachments

Uploads are **off by default**. Set `UPLOADS_ENABLED=true` and run `python manage.py migrate`
to enable them. Set `UPLOAD_MAX_FILE_BYTES` to change the 5 MiB (5 × 1024 × 1024 bytes) per-file
default. The only accepted contents are PNG, JPEG, GIF, WebP, PDF, and UTF-8 text without binary
control characters. Image/PDF types are identified from their leading bytes; filename extensions
and client Content-Type headers never determine the stored type. This is signature validation,
not a full decoder or malware scan. Empty files and oversized bodies are rejected.

All endpoints require a session. Send `X-CSRFToken` on uploads and deletes (fetch
`/api/auth/csrf/` first).

| Method and path | Result |
|---|---|
| `GET /api/projects/<id>/attachments/` | List metadata, including an owner-checked `download_url` |
| `POST /api/projects/<id>/attachments/` | Multipart form with one `file` field; HTTP 201 with metadata |
| `GET /api/projects/<id>/attachments/<file-id>/download/` | Stream the file with attachment disposition |
| `DELETE /api/projects/<id>/attachments/<file-id>/` | Delete the attachment; HTTP 204 |

Projects and attachments belonging to another user return 404, including uploads to someone
else's project. Owner and metadata always come from the session and inspected file. The
`max_files` plan limit counts attachments across **all** of a user's projects. Free plans
default to 10 even on existing installations without that key; an explicit integer overrides
it. Other plans without the key have no count cap. Reaching the count returns HTTP 409, like
the project limit. Creation locks the user row while checking and saving.

## Storage

Default storage is local `FileSystemStorage` under the git-ignored `media/` directory. Provision
persistent storage when running locally in containers. Storage names are random UUIDs and never
use the original filename as a path. The original basename is stored only as metadata and used
as the download filename. API serializers expose no storage URL. Do **not** add a public
`MEDIA_URL` route or configure a public web-server alias for this directory.

Downloads always stream through the owner-checked endpoint, with the inspected content type,
`Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, and
`Cache-Control: private, no-store`. No public or signed object-storage URLs are returned.

Setting `GS_BUCKET_NAME` selects `django-storages[google]` with private ACLs (`default_acl=None`)
and authenticated object access. The storage client loads lazily when used. On Cloud Run,
use Application Default Credentials from the runtime service account; no key file is needed.
The bucket must have uniform bucket-level access and public access prevention enabled. Grant
the runtime service account `roles/storage.objectUser` on the attachment bucket only. Keep
the attachment bucket separate from the database backup bucket. Deploy-script follow-up is
recorded in `RESULT.md`; the deploy script is unchanged by this task.

Deleting an attachment, project, or account schedules deletion of its stored files after the
database transaction commits, including ORM cascade/admin deletion. Rolling back a transaction
keeps the file. A failed API creation cleans up its storage write. Storage and SQL cannot commit
atomically: an abrupt process termination or failed storage deletion can leave an orphan. For
deployments needing stronger guarantees, add an outbox cleanup job and periodic reconciliation.
Tests use temporary local storage and never contact GCS.
