"""URL configuration for the resources app."""

from django.urls import path

from .views import ResourceViewSet

resource_list = ResourceViewSet.as_view(
    {
        "get": "list",
        "post": "create",
    }
)
resource_detail = ResourceViewSet.as_view(
    {
        "get": "retrieve",
        "patch": "partial_update",
        "delete": "destroy",
    }
)
resource_download = ResourceViewSet.as_view(
    {
        "get": "download",
    }
)
resource_processing_status = ResourceViewSet.as_view(
    {
        "get": "processing_status",
        "post": "processing_status",
    }
)

urlpatterns = [
    path(
        "libraries/<uuid:library_pk>/resources/",
        resource_list,
        name="resource-list",
    ),
    path(
        "libraries/<uuid:library_pk>/resources/<uuid:pk>/",
        resource_detail,
        name="resource-detail",
    ),
    path(
        "libraries/<uuid:library_pk>/resources/<uuid:pk>/download/",
        resource_download,
        name="resource-download",
    ),
    path(
        "libraries/<uuid:library_pk>/resources/<uuid:pk>/processing-status/",
        resource_processing_status,
        name="resource-processing-status",
    ),
]
