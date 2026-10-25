# Customizing

## Rename the project

```bash
python scripts/rename_project.py "Acme Cloud"            # dry run: lists files
python scripts/rename_project.py "Acme Cloud" --apply    # rewrite
git diff                                                  # review
```

It replaces the display name ("Django SaaS Starter") and slug ("django-saas-starter") in text
files. It never touches `LICENSE`, `CHANGELOG.md`, `.git`, `.env` or virtual environments, and it
skips the `config/` and `apps/` Python packages on purpose (renaming importable packages is
riskier than it is worth; do it by hand with your editor if you need to). Also update the
copyright holder in `LICENSE`, `SECURITY.md` contacts and the GitHub `OWNER` placeholders.

## Add an app

1. `mkdir apps/tasks && python manage.py startapp tasks apps/tasks`, then set `name = "apps.tasks"`
   in its `apps.py`.
2. Add `"apps.tasks"` to `INSTALLED_APPS` and a route in `config/urls.py`.
3. Copy the pattern from `apps/example`: serializer without an `owner` field, a viewset whose
   `get_queryset` filters by `request.user`, and `perform_create` that sets the owner and checks
   the plan limit with `get_plan`.
4. `python manage.py makemigrations`, then write tests for ownership (404), limits (409) and
   validation, as in `tests/test_example_api.py`.

## Add a plan limit

Add a key to the plan's `limits` in the admin (e.g. `{"max_items": 20, "max_exports": 5}`) and
read it with `get_limit(user, "max_exports")`. `None` means no limit configured.

## Add a background job

Create `apps/<name>/jobs.py`:

```python
from apps.core.job_registry import job


@job("send_digests")
def send_digests() -> None: ...
```

Run it with `python manage.py runjobs send_digests` from cron. See `python manage.py runjobs --list`.

## Send email

`apps.core.email.send_email(to, subject, "template_name", context)` renders
`templates/emails/template_name.txt` and an optional `.html` alternative.
