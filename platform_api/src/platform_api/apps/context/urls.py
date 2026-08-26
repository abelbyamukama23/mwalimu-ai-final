"""URL routes for the Mwalimu context domain."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from platform_api.apps.context.views import (
    ContextResourceViewSet,
    GeographicUnitViewSet,
    InstitutionContextRegionViewSet,
    UserFamiliarRegionViewSet,
)

router = DefaultRouter()
router.register(
    r"context/geographic-units",
    GeographicUnitViewSet,
    basename="context-geographic-unit",
)
router.register(
    r"context/familiar-regions",
    UserFamiliarRegionViewSet,
    basename="context-familiar-region",
)
router.register(
    r"context/resources",
    ContextResourceViewSet,
    basename="context-resource",
)

urlpatterns = [
    path("", include(router.urls)),
    path(
        "institutions/<uuid:institution_id>/context-regions/",
        InstitutionContextRegionViewSet.as_view({"get": "list", "post": "create"}),
        name="institution-context-region-list",
    ),
    path(
        "institutions/<uuid:institution_id>/context-regions/<uuid:pk>/",
        InstitutionContextRegionViewSet.as_view({"delete": "destroy"}),
        name="institution-context-region-detail",
    ),
    path(
        "institutions/<uuid:institution_id>/context-regions/reorder/",
        InstitutionContextRegionViewSet.as_view({"put": "reorder"}),
        name="institution-context-region-reorder",
    ),
]
