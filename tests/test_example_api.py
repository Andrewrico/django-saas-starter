import pytest
from rest_framework.test import APIClient

from apps.billing.models import Plan, Subscription
from apps.example.models import Project

pytestmark = pytest.mark.django_db
URL = "/api/projects/"


def create(client, name="P", **extra):
    return client.post(URL, {"name": name, **extra}, format="json")


def test_requires_authentication(api):
    assert api.get(URL).status_code == 403
    assert create(api).status_code == 403


def test_crud_roundtrip(auth_api, user):
    resp = create(auth_api, description="d", data={"k": 1})
    assert resp.status_code == 201
    pid = resp.json()["id"]
    assert Project.objects.get(pk=pid).owner == user
    assert auth_api.get(f"{URL}{pid}/").json()["name"] == "P"
    assert auth_api.patch(f"{URL}{pid}/", {"name": "Renamed"}, format="json").json()["name"] == "Renamed"
    assert auth_api.get(URL).json()["count"] == 1
    assert auth_api.delete(f"{URL}{pid}/").status_code == 204
    assert auth_api.get(URL).json()["count"] == 0


def test_owner_comes_from_session_not_payload(auth_api, user, make_user):
    other = make_user("bob@example.com")
    resp = create(auth_api, owner=other.pk, owner_id=other.pk)
    assert resp.status_code == 201
    assert Project.objects.get(pk=resp.json()["id"]).owner == user
    assert "owner" not in resp.json()


def test_other_users_objects_are_404(auth_api, make_user):
    bob = make_user("bob@example.com")
    theirs = Project.objects.create(owner=bob, name="secret")
    detail = f"{URL}{theirs.pk}/"
    assert auth_api.get(detail).status_code == 404
    assert auth_api.patch(detail, {"name": "x"}, format="json").status_code == 404
    assert auth_api.delete(detail).status_code == 404
    assert auth_api.get(URL).json()["count"] == 0
    theirs.refresh_from_db()
    assert theirs.name == "secret"


def test_free_plan_limit_returns_409(auth_api):
    for i in range(20):
        assert create(auth_api, name=f"p{i}").status_code == 201
    resp = create(auth_api, name="one too many")
    assert resp.status_code == 409
    assert "Free plan allows at most 20" in resp.json()["detail"]
    assert Project.objects.count() == 20


def test_limit_is_per_user(auth_api, make_user):
    bob = APIClient()
    bob.force_login(make_user("bob@example.com"))
    for i in range(20):
        create(auth_api, name=f"p{i}")
    assert create(bob).status_code == 201


def test_paid_plan_raises_limit(auth_api, user):
    for i in range(20):
        create(auth_api, name=f"p{i}")
    pro = Plan.objects.get(slug="pro")
    Subscription.objects.create(user=user, plan=pro, status="active")
    assert create(auth_api, name="21st").status_code == 201


def test_unlimited_plan_without_max_items(auth_api, user):
    plan = Plan.objects.create(slug="unl", name="Unlimited", limits={})
    Subscription.objects.create(user=user, plan=plan, status="active")
    assert create(auth_api).status_code == 201


def test_field_size_limits(auth_api):
    assert create(auth_api, name="x" * 121).status_code == 400
    assert create(auth_api, name="   ").status_code == 400
    assert create(auth_api, description="x" * 2001).status_code == 400
    assert create(auth_api, data={"blob": "x" * 5000}).status_code == 400
    assert create(auth_api, data=[1, 2]).status_code == 400
    assert create(auth_api, data={"ok": "x" * 100}).status_code == 201
