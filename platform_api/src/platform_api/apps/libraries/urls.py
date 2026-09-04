from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    InvitationAcceptView,
    InvitationDeclineView,
    LibraryAccessPolicyViewSet,
    LibraryInvitationViewSet,
    LibraryViewSet,
    PublicInvitationResolutionView,
)

router = DefaultRouter()
router.register(r"libraries", LibraryViewSet, basename="library")

# Nested access-policy routes under libraries.
access_policy_list = LibraryAccessPolicyViewSet.as_view(
    {
        "get": "list",
        "post": "create",
    }
)
access_policy_detail = LibraryAccessPolicyViewSet.as_view(
    {
        "get": "retrieve",
        "patch": "partial_update",
        "delete": "destroy",
    }
)

# Nested invitation routes under libraries.
invitation_list = LibraryInvitationViewSet.as_view(
    {
        "get": "list",
        "post": "create",
    }
)
invitation_detail = LibraryInvitationViewSet.as_view(
    {
        "get": "retrieve",
    }
)
invitation_revoke = LibraryInvitationViewSet.as_view(
    {
        "post": "revoke",
    }
)

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
    path(
        "libraries/<uuid:library_pk>/invitations/",
        invitation_list,
        name="library-invitation-list",
    ),
    path(
        "libraries/<uuid:library_pk>/invitations/<uuid:pk>/",
        invitation_detail,
        name="library-invitation-detail",
    ),
    path(
        "libraries/<uuid:library_pk>/invitations/<uuid:pk>/revoke/",
        invitation_revoke,
        name="library-invitation-revoke",
    ),
    path(
        "libraries/<uuid:library_pk>/invitations/<uuid:pk>/accept/",
        InvitationAcceptView.as_view(),
        name="library-invitation-scoped-accept",
    ),
    path(
        "libraries/<uuid:library_pk>/invitations/<uuid:pk>/decline/",
        InvitationDeclineView.as_view(),
        name="library-invitation-scoped-decline",
    ),
    # Public & direct invitation resolution and acceptance by secure token
    path(
        "invitations/<str:token>/",
        PublicInvitationResolutionView.as_view(),
        name="invitation-resolve",
    ),
    path(
        "invitations/<str:token>/accept/",
        InvitationAcceptView.as_view(),
        name="invitation-accept",
    ),
    path(
        "invitations/<str:token>/decline/",
        InvitationDeclineView.as_view(),
        name="invitation-decline",
    ),
]

