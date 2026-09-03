"""Views for the memberships app."""

import uuid
from typing import Any

from django.db import models
from django.db.models import QuerySet
from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response

from platform_api.apps.users.models import User

from .models import Membership, MembershipRole, MembershipStatus
from .serializers import MembershipSerializer


def _is_institution_admin(user: User | Any, institution_id: uuid.UUID) -> bool:
    """Return True if the user is an active administrator of the institution."""
    if not isinstance(user, User):
        return False
    return Membership.objects.filter(
        user=user,
        institution_id=institution_id,
        role=MembershipRole.ADMINISTRATOR,
        status=MembershipStatus.ACTIVE,
    ).exists()


class MembershipViewSet(viewsets.ModelViewSet):  # type: ignore[type-arg]
    """View set for managing memberships.

    Users may request their own student memberships. Institution administrators
    may list, retrieve, update, and delete memberships within their institution.
    """

    serializer_class = MembershipSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self) -> QuerySet[Membership]:
        """Return memberships visible to the authenticated user.

        If institution_id is passed via query params or X-Institution-Id header,
        it scopes the results to that institution:
        - If the caller is an active administrator of that institution, return all
          memberships for that institution.
        - If the caller is a member but not admin, return only their own membership.
        - If the caller is not a member, return empty queryset.

        If no institution_id is specified, return the user's own memberships plus
        all memberships in institutions where the user is an active administrator.
        """
        user = self.request.user
        if not isinstance(user, User):
            return Membership.objects.none()

        institution_param = (
            self.request.query_params.get("institution_id")
            or self.request.headers.get("X-Institution-Id")
        )
        if institution_param:
            try:
                target_inst_id = uuid.UUID(str(institution_param))
            except (ValueError, TypeError):
                return Membership.objects.none()

            is_admin = Membership.objects.filter(
                user=user,
                institution_id=target_inst_id,
                role=MembershipRole.ADMINISTRATOR,
                status=MembershipStatus.ACTIVE,
            ).exists()

            if is_admin:
                return Membership.objects.filter(
                    institution_id=target_inst_id
                ).order_by("-created_at")
            else:
                return Membership.objects.filter(
                    user=user,
                    institution_id=target_inst_id,
                ).order_by("-created_at")

        admin_institution_ids = Membership.objects.filter(
            user=user,
            role=MembershipRole.ADMINISTRATOR,
            status=MembershipStatus.ACTIVE,
        ).values_list("institution_id", flat=True)

        return Membership.objects.filter(
            models.Q(user=user) | models.Q(institution_id__in=admin_institution_ids),
        ).order_by("-created_at")

    def _admin_required(self, membership: Membership) -> None:
        """Raise PermissionDenied when the request user is not an institution admin."""
        if not _is_institution_admin(self.request.user, membership.institution_id):
            raise PermissionDenied(
                "You do not have permission to manage memberships in this institution.",
            )

    def update(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Only institution administrators may update memberships."""
        membership = self.get_object()
        self._admin_required(membership)
        return super().update(request, *args, **kwargs)

    def partial_update(
        self, request: Request, *args: object, **kwargs: object
    ) -> Response:
        """Only institution administrators may partially update memberships."""
        membership = self.get_object()
        self._admin_required(membership)
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Only institution administrators may delete memberships."""
        membership = self.get_object()
        self._admin_required(membership)
        if (
            membership.role == MembershipRole.ADMINISTRATOR
            and membership.status == MembershipStatus.ACTIVE
        ):
            active_admins = (
                Membership.objects.filter(
                    institution_id=membership.institution_id,
                    role=MembershipRole.ADMINISTRATOR,
                    status=MembershipStatus.ACTIVE,
                )
                .exclude(pk=membership.pk)
                .count()
            )
            if active_admins == 0:
                from rest_framework.exceptions import ValidationError

                raise ValidationError(
                    "Cannot remove the final active administrator of an institution."
                )
        return super().destroy(request, *args, **kwargs)

    def get_serializer_context(self) -> dict[str, Any]:
        """Include the current request in serializer context."""
        context = super().get_serializer_context()
        context["request"] = self.request
        return context
