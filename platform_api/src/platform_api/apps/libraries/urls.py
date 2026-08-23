"""URL configuration for the libraries app."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import LibraryAccessPolicyViewSet, LibraryViewSet

router = DefaultRouter()
router.register(r"libraries", LibraryViewSet, basename="library")

# Nested access-policy routes under libraries.
access_policy_list = LibraryAccessPolicyViewSet.as_view({
    "get": "list",
    "post": "create",
})
access_policy_detail = LibraryAccessPolicyViewSet.as_view({
    "get": "retrieve",
    "patch": "partial_update",
    "delete": "destroy",
})

urlpatterns = [
    *router.urls,
    path(
        "libraries/<uuid:library_pk>/access-policies/",
        access_policy_list,
        name="library-accesspolicy-list",
    ),
    path(
        "libraries/<uuid:library_pk>/access-policies/<uuid:pk>/",
        access_policy_detail,
        name="library-accesspolicy-detail",
    ),
]
