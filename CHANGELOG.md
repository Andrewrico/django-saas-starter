# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[0.1.0]: https://github.com/Andrewrico/django-saas-starter/releases/tag/v0.1.0
