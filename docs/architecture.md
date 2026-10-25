# Architecture

A conventional Django project: `config/` holds settings and URLs, `apps/` holds four small apps.

```text
browser / API client
        |
  SecurityMiddleware, WhiteNoise, sessions, CSRF, auth, allauth, SecurityHeaders
        |
  config/urls.py --> accounts (pages + /api/auth/)   billing (/api/billing/)
                 --> example (/api/projects/)         core (/healthz)
                 --> allauth (/accounts/...)          admin, OpenAPI
        |
  Django ORM --> Postgres (DATABASE_URL) or SQLite in development
```

## Apps

| App | Responsibility |
|---|---|
| `accounts` | `User` (email login), signup/login/logout/me/delete use-cases in `services.py`, JSON views in `api_views.py`, HTML views in `views.py` |
| `billing` | `Plan`, `Subscription`, `StripeEvent`; `limits.get_plan(user)`; Stripe calls in `services.py`; the only Stripe import is in `stripe_client.py` |
| `example` | `Project`: the pattern for owner-scoped resources with plan limits |
| `core` | health check, security-header middleware, auth throttle, `job_registry` + `runjobs`, `send_email` |

## Design decisions

- **Sessions + CSRF, not tokens.** Simple and safe for same-site browser apps. Credential
  endpoints (`signup`, `login`) re-enable CSRF protection that DRF would otherwise skip for
  anonymous callers. Fetch `/api/auth/csrf/` first and send `X-CSRFToken`.
- **One entry point for plans.** Call `get_plan(user)` or `get_limit(user, "key")`; never read
  `Subscription` directly in feature code. Only `active` and `trialing` subscriptions count.
- **Ownership by construction.** Querysets are filtered by `request.user` (other users' objects
  are 404) and serializers have no `owner` field, so it cannot be set from a payload.
- **Limit races.** `example` locks the user row inside a transaction while counting. This is
  effective on Postgres; SQLite serialises writes anyway.
- **No broker.** Background work is plain functions registered with `@job("name")` and run by
  `python manage.py runjobs` (cron, scheduler or `--loop`).
- **Static files** via WhiteNoise (manifest storage when `DEBUG` is off; `collectstatic` runs in
  the Docker build).
- **Security headers**: Django's `SecurityMiddleware` plus `apps.core.middleware` for CSP and
  Permissions-Policy. CSP is skipped for `/api/docs/` and `/admin/` because they use inline
  scripts/styles; edit `CSP_EXEMPT_PREFIXES` to change that.
