# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-10-31

### Added
- Google and GitHub sign-in through django-allauth, off until a provider's client id and secret
  are set; POST-only start, no auto-linking to existing password accounts, no stored tokens.
  Unconfigured providers return 404.
- Landing page with features, FAQ and pricing generated from public plans; `Plan.price_label`
  and `Plan.limit_lines()`; "Pricing" link in the header.
- Optional SQLite backups with Litestream 0.5.17 in the Docker image (`LITESTREAM_REPLICA_URL`),
  restore-on-start entrypoint, and SQLite WAL / `BEGIN IMMEDIATE` defaults.
- `scripts/deploy_cloudrun.sh`: Cloud Run + Cloud Storage + Secret Manager deploy, dry run by
  default.
- Scheduled jobs trigger `POST /internal/jobs/run/` (off by default): Google Cloud Scheduler OIDC
  tokens (signature, issuer, audience, service account checked) or a 32+ character bearer token;
  runs all or selected jobs, 500 when one fails. The deploy script creates a daily Cloud
  Scheduler job with its own role-less service account.

- "Upgrade to ..." and "Manage billing" buttons on the account page and pricing cards
  (server-rendered POST to Stripe Checkout / portal, 303 redirect), plus return notices.
- AI assistant demo at `/ai/` (Claude via the `anthropic` SDK, lazy import): summarize, rewrite,
  ask; daily per-plan limit `ai_requests_per_day`; `AIRequest` usage log without user text;
  server-side refusal fallback. Off until `ANTHROPIC_API_KEY` is set.
- Playwright browser tests (`tests/e2e`, `make e2e`, separate CI job) for signup, login, profile,
  delete, pricing, mobile layout, social sign-in start and upgrade-to-checkout.
- `docs/payments.md`: how to add another payment provider behind the billing seam.
- Two-factor sign-in with authenticator apps and recovery codes (allauth MFA, encrypted secrets,
  replay protection), enforced on the login page, the JSON API (new `POST /api/auth/login/mfa/`),
  allauth, social login and the Django admin. Enrolment off by default (`MFA_ENROLLMENT_ENABLED`).
- Email change: add, verify and make primary; addresses used by another account are refused.
- Owner-scoped file attachments for the example API (`UPLOADS_ENABLED`): content-based type
  allowlist, size limit, per-plan `max_files`, private downloads, files deleted with their
  project or account; optional private Cloud Storage via `GS_BUCKET_NAME`.
- Blog app (Markdown + nh3 sanitising, drafts, Atom feed), `sitemap.xml`, `robots.txt`.
- Staff analytics dashboard at `/admin/dashboard/`; optional Plausible via `PLAUSIBLE_DOMAIN`.

### Changed
- `django-allauth` is installed with the `socialaccount` and `mfa` extras and needs 65.21+.
- The `/login/` page and `POST /api/auth/login/` now go through allauth's staged login. The API
  answers `401 {"mfa_required": true}` when a second factor is needed.
- The Docker image starts through `scripts/docker-entrypoint.sh` (commands passed to the
  container still run as given).

## [0.1.0] - 2026-10-25

### Added
- Custom email-as-login `User` model, JSON auth API (csrf, signup, login, logout, me, delete) and
  minimal server-rendered pages (home, login, signup, account settings, delete account).
- django-allauth integration: password reset, email verification (`none`/`optional`/`mandatory`),
  social providers documented but not enabled.
- `Plan`, `Subscription` and `StripeEvent` models, `get_plan(user)` helper, free plan by default.
- Optional Stripe Checkout, customer portal and signed, idempotent webhook (off unless
  `BILLING_ENABLED=true` and both Stripe keys are set; Stripe is imported lazily).
- Owner-scoped `Project` example API with per-plan limit (409) and JSON size limits.
- `/healthz`, CSP and Permissions-Policy headers, DRF throttling, `runjobs` job seam,
  transactional email helper, configured Django admin.
- OpenAPI schema (`/api/schema/`) and Swagger UI (`/api/docs/`, assets served locally).
- Dockerfile (multi-stage, non-root), docker-compose with Postgres, GitHub Actions CI, Dependabot,
  pre-commit, Makefile, `scripts/rename_project.py`.
- Test suite (pytest-django) with a 90% coverage gate on `apps/`.

[0.2.0]: https://github.com/Andrewrico/django-saas-starter/releases/tag/v0.2.0
[0.1.0]: https://github.com/Andrewrico/django-saas-starter/releases/tag/v0.1.0
