from django.urls import path
from rest_framework.routers import DefaultRouter

from .attachments import AttachmentDetailView, AttachmentDownloadView, AttachmentListView
from .views import ProjectViewSet

router = DefaultRouter()
router.register("", ProjectViewSet, basename="project")
urlpatterns = [
    path("<int:project_id>/attachments/", AttachmentListView.as_view(), name="attachment-list"),
    path("<int:project_id>/attachments/<int:pk>/", AttachmentDetailView.as_view(), name="attachment-detail"),
    path(
        "<int:project_id>/attachments/<int:pk>/download/",
        AttachmentDownloadView.as_view(),
        name="attachment-download",
    ),
    *router.urls,
]
