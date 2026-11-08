# Django SaaS Starter

A small, production-minded starting point for a SaaS in Django. Accounts with Google and GitHub
sign-in, plans with limits, a landing page with pricing, optional Stripe billing, an owner-scoped
API example, and a Cloud Run deploy with SQLite backed up by Litestream. Tests, CI and Docker included.
**Everyone is on the free plan and billing is off until you turn it on.**

> Status: **v0.2**. It is a starter to fork and adapt, not a framework. See the
> [roadmap](#roadmap) for what is not done.

## Why

Most SaaS starters pick a JavaScript stack. If your team knows Django, you can have the usual
first-week plumbing (email and social login, verified signup, plan limits, a landing page,
Stripe wiring, backups, a deploy script, tests) already done in a stack you can read end to end, with sensible security defaults.

## Features

- **Accounts**: custom user (email is the login, no username), JSON API (csrf, signup, login,
  logout, me, delete) plus minimal accessible server-rendered pages (login, signup, account
  settings, delete account; light/dark via `prefers-color-scheme`, no JS framework).
- **Auth**: django-allauth for password reset and email verification (`none`, `optional`,
  `mandatory` via one setting). **Google and GitHub sign-in** appear as soon as a provider's
  client id and secret are set; sign-in starts with a CSRF-protected POST, and a provider login
  is never auto-linked to an existing password account.
- **Two-factor sign-in (optional)**: authenticator-app codes and recovery codes (allauth MFA),
  enforced on every login path: pages, JSON API (two-step), allauth, social and Django admin.
  Enrolment is off until `MFA_ENROLLMENT_ENABLED=true`.
- **Email change**: add an address, verify it, make it primary; the login email follows.
- **Landing page**: hero, features, pricing generated from the public `Plan`s (name,
  `price_label`, limits), FAQ and call to action. Server-rendered, no JavaScript.
- **Upgrade flow**: "Upgrade to ..." and "Manage billing" buttons on the account page and pricing
  cards (POST + CSRF to Stripe Checkout / customer portal), with return messages. Shown only
  when billing is on.
- **AI assistant demo (optional)**: `/ai/` summarizes, rewrites or answers with Claude, with a
  daily per-plan limit and a usage log. Off until `ANTHROPIC_API_KEY` is set
  ([docs/ai.md](docs/ai.md)).
- **Plans**: `Plan` (slug, name, limits JSON) and `get_plan(user)`, used by limit checks.
- **Billing (optional, off by default)**: Stripe Checkout, customer portal and a signed,
  idempotent webhook. Disabled unless `BILLING_ENABLED=true` *and* both Stripe keys are set;
  Stripe is not even imported otherwise.
- **Example resource**: owner-scoped `Project` CRUD. Owner always comes from the session, other
  users' objects return 404, the free plan allows 20 (409 with a clear message), JSON fields are
  size-limited.
- **SQLite in production (optional)**: WAL mode and safe locking defaults, plus
  [Litestream](https://litestream.io) in the Docker image. Set `LITESTREAM_REPLICA_URL` and the
  container restores the database from object storage on start, migrates, and streams every
  change back.
- **Cloud Run deploy**: `scripts/deploy_cloudrun.sh` (dry run by default) sets up a private,
  versioned bucket, Secret Manager secrets, a least-privilege service account and the service.
- **File uploads (optional)**: owner-scoped attachments on the example `Project` API, type
  checked from file contents, per-plan `max_files`, downloads only through an owner check;
  local disk or a private Cloud Storage bucket ([docs/uploads.md](docs/uploads.md)).
- **Blog**: Markdown posts with drafts, Atom feed, `sitemap.xml` and `robots.txt`
  ([docs/blog.md](docs/blog.md)).
- **Staff dashboard**: `/admin/dashboard/` with signups, plans, subscriptions and activity from
  the database; optional Plausible analytics via `PLAUSIBLE_DOMAIN` ([docs/dashboard.md](docs/dashboard.md)).
- **Scheduled jobs**: register a function with `@job("name")`; run it with `runjobs` (cron) or
  the authenticated `POST /internal/jobs/run/` trigger. The Cloud Run script schedules a daily run
  with Cloud Scheduler (Google-signed OIDC token). No Celery or broker.
- **Ops**: `/healthz`, CSP and Permissions-Policy headers, DRF throttling on auth endpoints, transactional email helper, configured Django admin.
- **API docs**: OpenAPI at `/api/schema/`, Swagger UI at `/api/docs/` (assets served locally).
- **Tooling**: ruff, mypy (light), pytest-django with a 90% coverage gate, Playwright browser
  tests for the main journeys (`make e2e`), pre-commit, Makefile,
  GitHub Actions (lint, tests on Postgres, migration check, deploy check, Docker build),
  Dependabot, multi-stage non-root Dockerfile, docker-compose with Postgres.

## Quickstart

```bash
git clone <your-fork-url> my-saas && cd my-saas
make setup          # venv, dependencies, .env, migrations
make run            # http://127.0.0.1:8000
make test           # tests + coverage
make e2e            # browser tests (first: .venv/bin/python -m playwright install chromium)
python manage.py createsuperuser   # optional, for /admin/
```

Requires Python 3.12. Without `make`, see the Makefile for the equivalent commands.

## Project layout

```text
config/            settings (env driven), urls, wsgi/asgi
apps/
  accounts/        User model, auth API + pages, forms, services
  billing/         Plan, Subscription, StripeEvent, get_plan, Stripe views + webhook
  example/         Project: the owner-scoped CRUD pattern to copy
  core/            healthz, middleware, throttling, jobs registry + runjobs, email helper
templates/ static/ HTML (one base template) and a single CSS file
tests/             pytest suite
docs/              architecture, auth, billing, deployment, customizing
scripts/           rename_project.py, deploy_cloudrun.sh, docker-entrypoint.sh
litestream.yml     Litestream config (used only when LITESTREAM_REPLICA_URL is set)
requirements/      base.txt (runtime), dev.txt (tooling)
```

## Configuration

All settings come from environment variables (a local `.env` is read if present; real
environment variables win). Copy `.env.example` to start.

| Variable | Default | Purpose |
|---|---|---|
| `DEBUG` | `false` | `true` for local dev only |
| `SECRET_KEY` | none | **Required** when `DEBUG=false` (startup fails without it) |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hosts |
| `CSRF_TRUSTED_ORIGINS` | empty | Comma-separated origins (`https://app.example.com`) |
| `DATABASE_URL` | `sqlite:///db.sqlite3` | e.g. `postgres://user:pass@host:5432/db` |
| `DB_CONN_MAX_AGE` | `60` | Persistent DB connection seconds |
| `LITESTREAM_REPLICA_URL` | empty | Docker image: back up SQLite to `gs://`, `s3://` or `file://` (off when empty) |
| `DB_PATH` | `/data/db.sqlite3` | SQLite file used when `LITESTREAM_REPLICA_URL` is set |
| `MIGRATE_ON_START` | `true` | With Litestream: run `migrate` when the container starts |
| `JOBS_OIDC_AUDIENCE`, `JOBS_INVOKER_EMAIL` | empty | Cloud Scheduler auth for `/internal/jobs/run/` (set by the deploy script) |
| `JOBS_TRIGGER_TOKEN` | empty | Bearer token (32+ chars) for `/internal/jobs/run/` from any other scheduler |
| `ANTHROPIC_API_KEY` | empty | AI assistant demo (off when empty); also `AI_MODEL`, `AI_EFFORT`, `AI_MAX_INPUT_CHARS` |
| `MFA_ENROLLMENT_ENABLED` | `false` | Let users turn on two-factor sign-in (existing MFA is always enforced) |
| `UPLOADS_ENABLED`, `UPLOAD_MAX_FILE_BYTES` | `false`, 5 MB | File attachments API |
| `GS_BUCKET_NAME` | empty | Store uploads in this private Cloud Storage bucket instead of `media/` |
| `PLAUSIBLE_DOMAIN` | empty | Add Plausible analytics to public pages |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | empty | Google sign-in (off until both are set) |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | empty | GitHub sign-in (off until both are set) |
| `ACCOUNT_EMAIL_VERIFICATION` | `optional` | `none`, `optional` or `mandatory` |
| `EMAIL_BACKEND` | console | SMTP or an anymail backend in production |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` | local defaults | SMTP settings |
| `DEFAULT_FROM_EMAIL`, `SITE_NAME` | placeholders | Sender and product name |
| `TRUST_PROXY_SSL_HEADER` | `false` | Trust `X-Forwarded-Proto` (set `true` behind a TLS proxy) |
| `SECURE_SSL_REDIRECT` | `true` unless `DEBUG` | Redirect HTTP to HTTPS (`/healthz` exempt) |
| `SECURE_HSTS_SECONDS` | `31536000` unless `DEBUG` | HSTS max-age |
| `SECURE_HSTS_PRELOAD` | `false` | Opt in only if you understand preload |
| `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` | `true` unless `DEBUG` | Secure cookies |
| `CONTENT_SECURITY_POLICY` | self-only policy | Override the CSP header |
| `THROTTLE_AUTH`, `THROTTLE_ANON`, `THROTTLE_USER` | `10/min`, `60/min`, `300/min` | DRF rates |
| `BILLING_ENABLED` | `false` | Master switch for Stripe |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | empty | Both required for billing |
| `BILLING_SUCCESS_URL`, `BILLING_CANCEL_URL`, `BILLING_PORTAL_RETURN_URL` | localhost URLs | Stripe redirects |
| `LOG_LEVEL` | `INFO` | Root log level |
| `DJANGO_READ_DOT_ENV_FILE` | `true` | `false` to ignore `.env` (tests do) |

## Enabling billing

Short version (full guide in [docs/billing.md](docs/billing.md)): create a Product and recurring
Price in Stripe, put the Price id on the `pro` plan in the admin, set `BILLING_ENABLED=true`,
`STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`, and point a Stripe webhook at
`/api/billing/webhook/`. Test in Stripe test mode first.

## Deploying

The image runs gunicorn as a non-root user, listens on `$PORT`, and serves static files with
WhiteNoise. Set `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` and, behind a
TLS-terminating proxy, `TRUST_PROXY_SSL_HEADER=true`. Then pick a database:

- **SQLite + Litestream** (small apps, one instance): set `LITESTREAM_REPLICA_URL`. On Google
  Cloud Run, `scripts/deploy_cloudrun.sh` does the whole setup; run it without `--apply` first to
  review every command.
- **Postgres**: set `DATABASE_URL` and run `python manage.py migrate` on each release.

Details, the restore drill and the trade-offs are in [docs/deployment.md](docs/deployment.md).

## Documentation

[Architecture](docs/architecture.md) | [Auth](docs/auth.md) | [Billing](docs/billing.md) |
[Deployment](docs/deployment.md) | [Customizing](docs/customizing.md) | [AI demo](docs/ai.md) |
[Payment providers](docs/payments.md) | [Uploads](docs/uploads.md) | [Blog](docs/blog.md) | [Dashboard](docs/dashboard.md)

## Roadmap

Nothing below is implemented in v0.2.

- [ ] WebAuthn / passkeys (allauth supports them; only TOTP + recovery codes are wired)
- [ ] More social providers (any allauth provider works; Google and GitHub are wired)
- [ ] Other payment providers (design notes in [docs/payments.md](docs/payments.md))
- [ ] Organizations / teams and seat-based plans
- [ ] Usage metering beyond simple per-plan counts
- [ ] Optional Celery/RQ integration for the jobs seam
- [ ] Token authentication for non-browser API clients
- [ ] Other payment providers
- [ ] Verified deployment recipes for Cloud Run and Fly

## FAQ

**Is this a drop-in alternative to Open SaaS or Wasp?** No. [Open SaaS](https://opensaas.sh) is a
full-featured template built on the Wasp framework (React, Node, Prisma), and as far as we know
it ships more out of the box (landing page, richer admin dashboard, more payment integrations,
example integrations). This project is deliberately smaller: a Django back end with the core
account, plan and billing plumbing. Check Open SaaS's own docs for its current feature list.

**Why pick this over Open SaaS?** Only if you want Python and Django, server-rendered pages or
your own front end, and a codebase small enough to read in an afternoon. If you want a
batteries-included JavaScript starter, Open SaaS is likely the better fit.

**Is there a front end?** Only minimal server-rendered pages. The JSON API uses session cookies
and CSRF, so a same-site SPA works; cross-site setups need extra work (not covered).

**Do I need Stripe?** No. Without it everyone stays on the free plan.

**Do I need Celery?** No. `runjobs` runs registered functions from cron or a loop.

**Is it production ready?** It applies sensible defaults and is tested, but nobody has audited
it for your use. Review the code, your threat model and [SECURITY.md](SECURITY.md) first.

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md).
Released under the [MIT License](LICENSE).
