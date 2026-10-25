import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import User

PASSWORD = "correct-horse-battery-9"


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def make_user(db):
    def _make(email: str = "alice@example.com", **extra) -> User:
        return User.objects.create_user(email=email, password=PASSWORD, **extra)

    return _make


@pytest.fixture
def user(make_user) -> User:
    return make_user()


@pytest.fixture
def auth_api(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client
