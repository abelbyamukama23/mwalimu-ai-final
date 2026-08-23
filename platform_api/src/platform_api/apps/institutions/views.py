"""Views for the institutions app."""

from typing import Any

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

from .models import Institution
from .serializers import InstitutionSerializer


def _is_institution_admin(user: User | Any, institution: Institution) -> bool:
    """Return True if the user is an active administrator of the institution."""
    if not isinstance(user, User):
        return False
    return Membership.objects.filter(
        user=user,
        institution=institution,
        role=MembershipRole.ADMINISTRATOR,
        status=MembershipStatus.ACTIVE,
    ).exists()


class InstitutionViewSet(viewsets.ModelViewSet):  # type: ignore[type-arg]
    """View set for institution management.

    Any authenticated user may discover institutions. Any authenticated user may
    create an institution and become its first administrator. Only institution
    administrators may update or delete an institution.
    """

    serializer_class = InstitutionSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self) -> QuerySet[Institution]:
        """Return all institutions ordered by creation date."""
        return Institution.objects.all().order_by("-created_at")

    def perform_create(self, serializer: BaseSerializer[Any]) -> None:
        """Create the institution and make the requester its first admin."""
        institution = serializer.save()
        user = self.request.user
        if isinstance(user, User):
            Membership.objects.create(
                user=user,
                institution=institution,
                role=MembershipRole.ADMINISTRATOR,
                status=MembershipStatus.ACTIVE,
            )

    def update(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Only institution administrators may update an institution."""
        institution = self.get_object()
        if not _is_institution_admin(request.user, institution):
            raise PermissionDenied(
                "You do not have permission to update this institution.",
            )
        return super().update(request, *args, **kwargs)

    def partial_update(
        self, request: Request, *args: object, **kwargs: object
    ) -> Response:
        """Only institution administrators may partially update an institution."""
        institution = self.get_object()
        if not _is_institution_admin(request.user, institution):
            raise PermissionDenied(
                "You do not have permission to update this institution.",
            )
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Only institution administrators may delete an institution."""
        institution = self.get_object()
        if not _is_institution_admin(request.user, institution):
            raise PermissionDenied(
                "You do not have permission to delete this institution.",
            )
        return super().destroy(request, *args, **kwargs)
