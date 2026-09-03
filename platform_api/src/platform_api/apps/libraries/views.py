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
from .models import (
    Library,
    LibraryAccessPolicy,
    LibraryScopeType,
    LibraryStatus,
    LibraryVisibility,
)
from .serializers import LibraryAccessPolicySerializer, LibrarySerializer


class LibraryViewSet(viewsets.ModelViewSet):  # type: ignore[type-arg]
    """View set for library management.

    Supports both personal libraries (owned by individual users) and
    institutional libraries (owned by institutions and managed by
    institution administrators).
    """

    serializer_class = LibrarySerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self) -> QuerySet[Library]:
        """Return libraries the user is authorized to view.

        Returns personal libraries owned by the user, plus institutional
        libraries authorized through administrator memberships, discoverability,
        or explicit access policies.
        """
        user = self.request.user
        if not isinstance(user, User):
            return Library.objects.none()

        granted_library_ids = LibraryAccessPolicy.objects.filter(
            user=user,
        ).values_list("library_id", flat=True)

        institution_param = (
            self.request.query_params.get("institution_id")
            or self.request.headers.get("X-Institution-Id")
        )
        if institution_param:
            try:
                target_inst_id = uuid.UUID(str(institution_param))
            except (ValueError, TypeError):
                return Library.objects.none()

            is_admin = Membership.objects.filter(
                user=user,
                institution_id=target_inst_id,
                role=MembershipRole.ADMINISTRATOR,
                status=MembershipStatus.ACTIVE,
            ).exists()

            if is_admin:
                return Library.objects.filter(
                    institution_id=target_inst_id,
                    scope_type=LibraryScopeType.INSTITUTION,
                    status=LibraryStatus.ACTIVE,
                ).order_by("-created_at")

            is_member = Membership.objects.filter(
                user=user,
                institution_id=target_inst_id,
                status=MembershipStatus.ACTIVE,
            ).exists()

            if is_member:
                return (
                    Library.objects.filter(
                        institution_id=target_inst_id,
                        scope_type=LibraryScopeType.INSTITUTION,
                        status=LibraryStatus.ACTIVE,
                    )
                    .filter(
                        models.Q(visibility=LibraryVisibility.DISCOVERABLE)
                        | models.Q(id__in=granted_library_ids)
                    )
                    .order_by("-created_at")
                )

            return Library.objects.none()

        personal_q = models.Q(
            scope_type=LibraryScopeType.PERSONAL,
            owner=user,
        )

        admin_institution_ids = Membership.objects.filter(
            user=user,
            role=MembershipRole.ADMINISTRATOR,
            status=MembershipStatus.ACTIVE,
        ).values_list("institution_id", flat=True)

        member_institution_ids = Membership.objects.filter(
            user=user,
            status=MembershipStatus.ACTIVE,
        ).values_list("institution_id", flat=True)

        institutional_q = models.Q(
            scope_type=LibraryScopeType.INSTITUTION,
        ) & (
            models.Q(institution_id__in=admin_institution_ids)
            | models.Q(
                institution_id__in=member_institution_ids,
                visibility=LibraryVisibility.DISCOVERABLE,
            )
            | models.Q(id__in=granted_library_ids)
        )

        return (
            Library.objects.filter(status=LibraryStatus.ACTIVE)
            .filter(personal_q | institutional_q)
            .order_by("-created_at")
        )

    def perform_create(self, serializer: BaseSerializer[Any]) -> None:
        """Create a personal or institutional library.

        When institution_id is provided, validates that the user is an active
        administrator of the institution. When institution_id is omitted,
        creates a personal library owned by request.user.
        """
        institution_id = serializer.validated_data.get("institution_id")
        if institution_id:
            if not is_institution_admin(self.request.user, institution_id):
                raise PermissionDenied(
                    "You do not have permission to create a library in "
                    "this institution.",
                )
            library = serializer.save(
                scope_type=LibraryScopeType.INSTITUTION,
                institution_id=institution_id,
                owner=None,
            )
            from platform_api.apps.institutions.audit import record_audit_event
            from platform_api.apps.institutions.models import AuditAction

            record_audit_event(
                institution=library.institution,
                action=AuditAction.LIBRARY_CREATED,
                target_type="library",
                target_id=library.id,
                target_repr=library.name,
                actor=self.request.user,
                metadata={"visibility": library.visibility, "slug": library.slug},
                request=self.request,
            )
        else:
            serializer.save(
                scope_type=LibraryScopeType.PERSONAL,
                owner=self.request.user,
                institution=None,
            )

    def update(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Only library managers may update a library."""
        library = self.get_object()
        if not can_manage_library(request.user, library):
            raise PermissionDenied(
                "You do not have permission to update this library.",
            )
        response = super().update(request, *args, **kwargs)
        if library.institution:
            from platform_api.apps.institutions.audit import record_audit_event
            from platform_api.apps.institutions.models import AuditAction

            record_audit_event(
                institution=library.institution,
                action=AuditAction.LIBRARY_UPDATED,
                target_type="library",
                target_id=library.id,
                target_repr=library.name,
                actor=request.user,
                metadata={"updated_fields": list(request.data.keys())},
                request=request,
            )
        return response

    def partial_update(
        self, request: Request, *args: object, **kwargs: object
    ) -> Response:
        """Only library managers may partially update a library."""
        library = self.get_object()
        if not can_manage_library(request.user, library):
            raise PermissionDenied(
                "You do not have permission to update this library.",
            )
        response = super().partial_update(request, *args, **kwargs)
        if library.institution:
            from platform_api.apps.institutions.audit import record_audit_event
            from platform_api.apps.institutions.models import AuditAction

            record_audit_event(
                institution=library.institution,
                action=AuditAction.LIBRARY_UPDATED,
                target_type="library",
                target_id=library.id,
                target_repr=library.name,
                actor=request.user,
                metadata={"updated_fields": list(request.data.keys())},
                request=request,
            )
        return response

    def destroy(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Only library managers may delete a library."""
        library = self.get_object()
        if not can_manage_library(request.user, library):
            raise PermissionDenied(
                "You do not have permission to delete this library.",
            )
        inst = library.institution
        lib_id = library.id
        lib_name = library.name
        response = super().destroy(request, *args, **kwargs)
        if inst:
            from platform_api.apps.institutions.audit import record_audit_event
            from platform_api.apps.institutions.models import AuditAction

            record_audit_event(
                institution=inst,
                action=AuditAction.LIBRARY_DELETED,
                target_type="library",
                target_id=lib_id,
                target_repr=lib_name,
                actor=request.user,
                metadata={"deleted_library": lib_name},
                request=request,
            )
        return response


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
        policy = serializer.save(library=library)
        if library.institution:
            from platform_api.apps.institutions.audit import record_audit_event
            from platform_api.apps.institutions.models import AuditAction

            record_audit_event(
                institution=library.institution,
                action=AuditAction.ACCESS_GRANTED,
                target_type="access_policy",
                target_id=policy.id,
                target_repr=f"{policy.user.email} -> {library.name}",
                actor=self.request.user,
                metadata={"role": policy.role, "user_email": policy.user.email},
                request=self.request,
            )

    def perform_update(self, serializer: BaseSerializer[Any]) -> None:
        """Update the policy."""
        policy = serializer.save()
        library = policy.library
        if library.institution:
            from platform_api.apps.institutions.audit import record_audit_event
            from platform_api.apps.institutions.models import AuditAction

            record_audit_event(
                institution=library.institution,
                action=AuditAction.ACCESS_UPDATED,
                target_type="access_policy",
                target_id=policy.id,
                target_repr=f"{policy.user.email} -> {library.name}",
                actor=self.request.user,
                metadata={"role": policy.role, "user_email": policy.user.email},
                request=self.request,
            )

    def perform_destroy(self, instance: Any) -> None:
        """Revoke the policy."""
        library = instance.library
        inst = library.institution
        policy_id = instance.id
        user_email = instance.user.email
        super().perform_destroy(instance)
        if inst:
            from platform_api.apps.institutions.audit import record_audit_event
            from platform_api.apps.institutions.models import AuditAction

            record_audit_event(
                institution=inst,
                action=AuditAction.ACCESS_REVOKED,
                target_type="access_policy",
                target_id=policy_id,
                target_repr=f"{user_email} -> {library.name}",
                actor=self.request.user,
                metadata={"revoked_user": user_email},
                request=self.request,
            )
