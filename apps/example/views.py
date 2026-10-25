from django.db import transaction
from django.db.models import QuerySet
from rest_framework import status, viewsets
from rest_framework.exceptions import APIException
from rest_framework.serializers import BaseSerializer

from apps.accounts.models import User
from apps.billing.limits import get_plan

from .models import Project
from .serializers import ProjectSerializer


class LimitReached(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "limit_reached"
    default_detail = "Plan limit reached."


class ProjectViewSet(viewsets.ModelViewSet):
    """CRUD for the caller's own projects.

    Rules to copy: the queryset is always filtered by ``request.user`` (so other
    users' objects are 404, not 403), and ``owner`` is set from the session.
    """

    serializer_class = ProjectSerializer

    def get_queryset(self) -> QuerySet[Project]:
        if getattr(self, "swagger_fake_view", False):  # schema generation has no real user
            return Project.objects.none()
        return Project.objects.filter(owner=self.request.user)

    def perform_create(self, serializer: BaseSerializer) -> None:
        with transaction.atomic():
            # Lock the user row so concurrent creates can't both slip under the limit.
            user = User.objects.select_for_update().get(pk=self.request.user.pk)
            plan = get_plan(user)
            max_items = plan.limit("max_items")
            if max_items is not None and Project.objects.filter(owner=user).count() >= max_items:
                raise LimitReached(
                    f"Your {plan.name} plan allows at most {max_items} projects. "
                    "Delete one or upgrade to create more."
                )
            serializer.save(owner=user)
