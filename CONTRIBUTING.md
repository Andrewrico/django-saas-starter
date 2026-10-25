# Contributing

Thanks for helping. Small, focused pull requests are easiest to review.

## Setup

```bash
make setup      # .venv, dev dependencies, .env, migrations
make test       # pytest with coverage (gate: 90% of apps/)
make lint       # ruff check, ruff format --check, mypy
make format     # auto-fix and format
pre-commit install   # optional: run ruff on every commit
```

## Ground rules

- Open an issue first for anything bigger than a bug fix, so we agree on scope. This project
  deliberately stays small; features that need a broker, a frontend framework or a third-party
  service should be optional and off by default.
- Add or update tests. New code in `apps/` must keep total coverage at or above 90%.
- Models changed? Commit the migration (`python manage.py makemigrations`); CI runs
  `makemigrations --check`.
- Never include secrets, real customer data or personal data in code, tests, fixtures or issues.
- Keep the owner-scoping rules in `apps/example` intact: owner comes from `request.user`, other
  users' objects return 404.
- Update `CHANGELOG.md` (Unreleased section) and the relevant file in `docs/`.

## Commit and PR style

Imperative, present-tense subject lines ("Add webhook retry test"). Fill in the PR template.

## Code of conduct

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
