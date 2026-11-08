# Deployment

## Required environment

`SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and `TRUST_PROXY_SSL_HEADER=true` if a
proxy terminates TLS (otherwise the HTTPS redirect loops). Configure a real `EMAIL_BACKEND`.
Database: either SQLite + Litestream (below) or Postgres via `DATABASE_URL`, with
`python manage.py migrate` on every release.

## Secure defaults when `DEBUG=false`

HTTPS redirect (except `/healthz`), secure session and CSRF cookies, HSTS one year with
subdomains, `nosniff`, `X-Frame-Options: DENY`, CSP and Permissions-Policy headers, and no
`SECRET_KEY` fallback. `manage.py check --deploy` reports no issues with a production-like
environment. **Intentional exception:** `security.W021` (HSTS preload) is silenced because
preload is hard to undo; opt in with `SECURE_HSTS_PRELOAD=true` and remove the silence.

## Docker

```bash
docker build -t my-saas .
docker run --rm -p 8000:8000 -e SECRET_KEY=... -e DATABASE_URL=... \
  -e ALLOWED_HOSTS=localhost -e SECURE_SSL_REDIRECT=false \
  -e SESSION_COOKIE_SECURE=false -e CSRF_COOKIE_SECURE=false my-saas
```

(The last three are only for trying it over plain HTTP.) `docker-compose.yml` starts the app with
Postgres for a local production-like run: `SECRET_KEY=... docker compose up --build`.
The image is multi-stage, runs as a non-root user, collects static files at build time and has a
`/healthz` healthcheck.

## SQLite + Litestream

For small apps that run as **one instance**, SQLite is fast, free and simple. The weak spot is
the disk: on Cloud Run (and most containers) it disappears when the instance stops.
[Litestream](https://litestream.io) fixes that by streaming every change to object storage.

The Docker image includes Litestream (v0.5.17, checksum-verified at build). It does nothing until
`LITESTREAM_REPLICA_URL` is set. Then `scripts/docker-entrypoint.sh`:

1. uses the SQLite file at `DB_PATH` (default `/data/db.sqlite3`); `DATABASE_URL` must be unset
   or point at that file,
2. restores it from the replica if the file is missing (a fresh instance),
3. runs `migrate` (turn off with `MIGRATE_ON_START=false`),
4. runs gunicorn under `litestream replicate`, which uploads changes every 5 seconds and does a
   final sync on shutdown (`SIGTERM`).

Settings switch SQLite to WAL mode with `synchronous=NORMAL`, a 5 s busy timeout and
`BEGIN IMMEDIATE` transactions, so concurrent writes wait instead of failing.

Replica URLs: `gs://bucket/db` (Cloud Storage, uses the service account), `s3://bucket/db`
(uses `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`), `file:///path` (local testing).

**Rules and trade-offs**

- **One instance only.** SQLite has a single writer and Litestream assumes one replicating
  process. Keep max instances at 1. When you need more, move to Postgres.
- **Deploy overlap.** During a rollout the old and new revision can run for a few seconds; writes
  to the old one in that window can be lost. Deploy at quiet times, or use Postgres if that
  matters.
- **Up to ~5 seconds of writes** can be lost if an instance is killed without a clean shutdown.
- Run one-off commands in the running container (`docker exec ... python manage.py ...`); with
  `LITESTREAM_REPLICA_URL` set, every process opens the same `DB_PATH` file.

**Restore drill (local, no cloud account needed)**

```bash
docker build -t my-saas .
docker volume create replica
docker run --rm -u root -v replica:/replica --entrypoint sh my-saas -c "chown app:app /replica"
ENV="-e SECRET_KEY=drill -e ALLOWED_HOSTS=localhost -e SECURE_SSL_REDIRECT=false -e LITESTREAM_REPLICA_URL=file:///replica/db"
docker run -d --name one $ENV -v replica:/replica my-saas
docker exec one python manage.py createsuperuser        # write something
sleep 6 && docker rm -f one                              # instance gone, /data with it
docker run -d --name two $ENV -v replica:/replica my-saas
docker exec two python manage.py shell -c "from apps.accounts.models import User; print(User.objects.all())"
```

The second container starts with an empty disk and restores the user from the replica. (In zsh,
write `${=ENV}` instead of `$ENV`.)

## Google Cloud Run (SQLite + Litestream)

`scripts/deploy_cloudrun.sh` prints every command by default; `--apply` runs them.

```bash
GCP_PROJECT=my-project SERVICE=my-saas ./scripts/deploy_cloudrun.sh               # review
SECRET_KEY=... GCP_PROJECT=my-project SERVICE=my-saas ./scripts/deploy_cloudrun.sh --apply
```

It enables the APIs, creates an Artifact Registry repo, a service account with **no
project-wide roles**, a private, versioned bucket (old versions deleted after 7 days) that only
that account can write, Secret Manager secrets (`SECRET_KEY` plus any of
`GOOGLE_CLIENT_SECRET`, `GITHUB_CLIENT_SECRET`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`,
`EMAIL_HOST_PASSWORD`, `ANTHROPIC_API_KEY`, `JOBS_TRIGGER_TOKEN` that are set), builds with Cloud Build and deploys with max 1 instance,
scale to zero and request-based CPU billing. It refuses `--apply` with uncommitted changes.
Every optional variable that is set in your shell is deployed, so unset what you don't want.
Settings: `REGION` (default `us-central1`), `BUCKET`, `HOST` (custom domain).

Status: the container, the restore cycle and the script's dry run are tested locally (Docker
with a `file://` replica). The script has not been run against a live Google Cloud project in
this repository's CI; review the dry run before `--apply`. Cloud Run, Cloud Storage and Secret
Manager have free tiers, but check current Google Cloud pricing for your usage.

### Scheduled jobs (Cloud Scheduler)

The script also creates a Cloud Scheduler job, `<service>-jobs`, that POSTs to
`https://<host>/internal/jobs/run/` (daily at 03:00 UTC by default; `JOBS_SCHEDULE` and
`JOBS_TIMEZONE` change it; `JOBS_SCHEDULE=off` skips it). The registered jobs run **inside the
web service**, so SQLite keeps a single writer and scale-to-zero still works.

Each call carries a Google-signed OIDC token issued to a dedicated service account,
`<service>-jobs`, that has no roles. The app checks the signature against Google's public keys,
the issuer, the expiry, the audience (`JOBS_OIDC_AUDIENCE`, the exact URL) and the account
(`JOBS_INVOKER_EMAIL`). Anything else gets 401. The script sets both variables. Whoever runs
`--apply` needs permission to act as that service account (project owners have it).

Check a run: Cloud Scheduler, `<service>-jobs`, "Force run", then the Cloud Run logs
(`Job ... finished`). A failed job returns 500, which Cloud Scheduler records as a failure.
Cloud Scheduler includes a small number of free jobs per billing account; check current pricing.

## Other PaaS (Fly, Render, ...)

- Point the platform's health check at `/healthz`; listen on `$PORT` (the image does).
- Set `TRUST_PROXY_SSL_HEADER=true` and keep `SECURE_SSL_REDIRECT` on.
- Use a managed Postgres (or SQLite + Litestream on one instance); keep `DB_CONN_MAX_AGE` modest
  on platforms with connection limits.
- Run migrations as a release step or one-off job, not on every instance start.
- Scheduled work: either run `python manage.py runjobs` from the platform's scheduler or cron
  (fine with Postgres), or call the HTTP trigger:

  ```bash
  # JOBS_TRIGGER_TOKEN: a random value of 32+ characters, stored in the platform's secret manager
  curl -fsS -X POST -H "Authorization: Bearer $JOBS_TRIGGER_TOKEN" https://<host>/internal/jobs/run/
  # one job only: add  -H 'Content-Type: application/json' -d '{"jobs": ["prune_stripe_events"]}'
  ```

  The endpoint returns 404 unless `JOBS_TRIGGER_TOKEN` or the Cloud Scheduler pair
  (`JOBS_OIDC_AUDIENCE` + `JOBS_INVOKER_EMAIL`) is set, and 401 without a valid token.
- Store secrets in the platform's secret manager, never in the image or repository.
