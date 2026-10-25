# Deployment

Generic guidance. These are not tested recipes for any specific platform.

## Required environment

`SECRET_KEY`, `DATABASE_URL` (Postgres), `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and
`TRUST_PROXY_SSL_HEADER=true` if a proxy terminates TLS (otherwise the HTTPS redirect loops).
Configure a real `EMAIL_BACKEND`. Run `python manage.py migrate` on every release.

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

## Cloud Run / Fly / similar PaaS

- Point the platform's health check at `/healthz`; listen on `$PORT` (the image does).
- Set `TRUST_PROXY_SSL_HEADER=true` and keep `SECURE_SSL_REDIRECT` on.
- Use a managed Postgres; keep `DB_CONN_MAX_AGE` modest on platforms with connection limits.
- Run migrations as a release step or one-off job, not on every instance start.
- Scheduled work: call `python manage.py runjobs` from the platform's scheduler (Cloud Scheduler
  with a Cloud Run job, `fly machines` schedule, cron).
- Store secrets in the platform's secret manager, never in the image or repository.
