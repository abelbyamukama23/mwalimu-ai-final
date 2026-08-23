"""Views for the libraries app."""

import uuid
from typing import Any

from django.db import models
from django.db.models import QuerySet
from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from platform_api.apps.memberships.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
)
from platform_api.apps.users.models import User

from .authz import can_manage_library, is_institution_admin
from .models import Library, LibraryAccessPolicy, LibraryStatus, LibraryVisibility
from .serializers import LibraryAccessPolicySerializer, LibrarySerializer


class LibraryViewSet(viewsets.ModelViewSet):  # type: ignore[type-arg]
    """View set for library management.

    Institution administrators may create, update, and delete libraries within
    their institution. Library administrators may update and delete libraries
    according to policy. Members may view discoverable libraries and libraries
    for which they hold an explicit access policy.
    """

    serializer_class = LibrarySerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self) -> QuerySet[Library]:
        """Return libraries the user is authorized to view.

        The queryset is scoped to the user's institution memberships and
        explicit library grants. Restricted libraries are never leaked to
        users without an explicit policy.
        """
        user = self.request.user
        if not isinstance(user, User):
            return Library.objects.none()

        admin_institution_ids = Membership.objects.filter(
            user=user,
            role=MembershipRole.ADMINISTRATOR,
            status=MembershipStatus.ACTIVE,
        ).values_list("institution_id", flat=True)

        member_institution_ids = Membership.objects.filter(
            user=user,
            status=MembershipStatus.ACTIVE,
        ).values_list("institution_id", flat=True)

        granted_library_ids = LibraryAccessPolicy.objects.filter(
            user=user,
        ).values_list("library_id", flat=True)

        return Library.objects.filter(status=LibraryStatus.ACTIVE).filter(
            models.Q(institution_id__in=admin_institution_ids)
            | models.Q(
                institution_id__in=member_institution_ids,
                visibility=LibraryVisibility.DISCOVERABLE,
            )
            | models.Q(id__in=granted_library_ids),
        ).order_by("-created_at")

    def perform_create(self, serializer: BaseSerializer[Any]) -> None:
        """Create the library under the requested institution.

        Only institution administrators may create libraries.
        """
        institution_id = serializer.validated_data.get("institution_id")
        if not is_institution_admin(self.request.user, institution_id):
            raise PermissionDenied(
                "You do not have permission to create a library in this institution.",
            )
        serializer.save()

    def update(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Only library managers may update a library."""
        library = self.get_object()
        if not can_manage_library(request.user, library):
            raise PermissionDenied(
                "You do not have permission to update this library.",
            )
        return super().update(request, *args, **kwargs)

    def partial_update(
        self, request: Request, *args: object, **kwargs: object
    ) -> Response:
        """Only library managers may partially update a library."""
        library = self.get_object()
        if not can_manage_library(request.user, library):
            raise PermissionDenied(
                "You do not have permission to update this library.",
            )
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Only library managers may delete a library."""
        library = self.get_object()
        if not can_manage_library(request.user, library):
            raise PermissionDenied(
                "You do not have permission to delete this library.",
            )
        return super().destroy(request, *args, **kwargs)


class LibraryAccessPolicyViewSet(viewsets.ModelViewSet):  # type: ignore[type-arg]
    """View set for managing library access policies.

    Only institution administrators and library administrators may view,
    create, update, or delete access policies for a library.
    """

    serializer_class = LibraryAccessPolicySerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "pk"

    def get_library(self) -> Library:
        """Return the library from the URL path parameter."""
        raw_library_id = self.kwargs.get("library_pk")
        library_id = uuid.UUID(str(raw_library_id))
        try:
            library = Library.objects.get(pk=library_id)
        except Library.DoesNotExist as exc:
            raise PermissionDenied("Library not found.") from exc

        if not can_manage_library(self.request.user, library):
            message = (
                "You do not have permission to manage access policies for this library."
            )
            raise PermissionDenied(message)
        return library

    def get_queryset(self) -> QuerySet[LibraryAccessPolicy]:
        """Return access policies for the library the user may manage."""
        library = self.get_library()
        return LibraryAccessPolicy.objects.filter(library=library).order_by(
            "-created_at"
        )

    def get_serializer_context(self) -> dict[str, Any]:
        """Include the library in serializer context."""
        context = super().get_serializer_context()
        context["library"] = self.get_library()
        return context

    def perform_create(self, serializer: BaseSerializer[Any]) -> None:
        """Create the policy scoped to the managed library."""
        library = self.get_library()
        serializer.save(library=library)
