"""Browser tests (Playwright). Not part of the default run: `pytest -m e2e --no-cov`.

One-time setup: `python -m playwright install chromium`.
"""

import os

import pytest

# Playwright's sync API runs an event loop in the test thread; Django's ORM calls in the tests
# themselves are still synchronous and safe.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


def pytest_collection_modifyitems(items):
    for item in items:
        if "tests/e2e/" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
