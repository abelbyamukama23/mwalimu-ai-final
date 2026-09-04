"""Views for the memberships app."""

import uuid
from typing import Any

from django.db import models
from django.db.models import QuerySet
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from platform_api.apps.institutions.audit import record_audit_event
from platform_api.apps.institutions.models import AcademicUnit, AuditAction
from platform_api.apps.users.models import User

from .models import (
    Membership,
    MembershipRole,
    MembershipStatus,
    TeachingAssignment,
    TeachingAssignmentStatus,
)
from .serializers import (
    AcademicUnitMinimalSerializer,
    MembershipSerializer,
    StudentPlacementSerializer,
    TeachingAssignmentSerializer,
)


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
        old_role = membership.role
        old_status = membership.status
        response = super().update(request, *args, **kwargs)
        membership.refresh_from_db()
        from platform_api.apps.institutions.audit import record_audit_event
        from platform_api.apps.institutions.models import AuditAction

        if old_role != membership.role:
            record_audit_event(
                institution=membership.institution,
                action=AuditAction.MEMBER_ROLE_CHANGED,
                target_type="membership",
                target_id=membership.id,
                target_repr=membership.user.email,
                actor=request.user if isinstance(request.user, User) else None,
                metadata={"old_role": old_role, "new_role": membership.role},
                request=request,
            )
        if old_status != membership.status:
            record_audit_event(
                institution=membership.institution,
                action=AuditAction.MEMBER_STATUS_CHANGED,
                target_type="membership",
                target_id=membership.id,
                target_repr=membership.user.email,
                actor=request.user if isinstance(request.user, User) else None,
                metadata={"old_status": old_status, "new_status": membership.status},
                request=request,
            )
        return response

    def partial_update(
        self, request: Request, *args: object, **kwargs: object
    ) -> Response:
        """Only institution administrators may partially update memberships."""
        membership = self.get_object()
        self._admin_required(membership)
        old_role = membership.role
        old_status = membership.status
        response = super().partial_update(request, *args, **kwargs)
        membership.refresh_from_db()
        from platform_api.apps.institutions.audit import record_audit_event
        from platform_api.apps.institutions.models import AuditAction

        if old_role != membership.role:
            record_audit_event(
                institution=membership.institution,
                action=AuditAction.MEMBER_ROLE_CHANGED,
                target_type="membership",
                target_id=membership.id,
                target_repr=membership.user.email,
                actor=request.user if isinstance(request.user, User) else None,
                metadata={"old_role": old_role, "new_role": membership.role},
                request=request,
            )
        if old_status != membership.status:
            record_audit_event(
                institution=membership.institution,
                action=AuditAction.MEMBER_STATUS_CHANGED,
                target_type="membership",
                target_id=membership.id,
                target_repr=membership.user.email,
                actor=request.user if isinstance(request.user, User) else None,
                metadata={"old_status": old_status, "new_status": membership.status},
                request=request,
            )
        return response

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
        inst = membership.institution
        user_email = membership.user.email
        mem_id = membership.id
        response = super().destroy(request, *args, **kwargs)
        from platform_api.apps.institutions.audit import record_audit_event
        from platform_api.apps.institutions.models import AuditAction

        record_audit_event(
            institution=inst,
            action=AuditAction.MEMBER_REMOVED,
            target_type="membership",
            target_id=mem_id,
            target_repr=user_email,
            actor=request.user if isinstance(request.user, User) else None,
            metadata={"removed_user": user_email},
            request=request,
        )
        return response

    def get_serializer_context(self) -> dict[str, Any]:
        """Include the current request in serializer context."""
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    @action(detail=True, methods=["get", "put"], url_path="academic-placement")
    def academic_placement(self, request: Request, pk: str | None = None) -> Response:
        """View or update a student's academic unit placement."""
        membership = self.get_object()

        if request.method == "GET":
            # Member can view their own placement; institution admins can view any member's placement
            is_self = isinstance(request.user, User) and membership.user_id == request.user.id
            is_admin = _is_institution_admin(request.user, membership.institution_id)
            if not (is_self or is_admin):
                raise PermissionDenied("You do not have permission to view this academic placement.")

            if not membership.academic_unit:
                return Response(None, status=status.HTTP_200_OK)
            return Response(
                AcademicUnitMinimalSerializer(membership.academic_unit).data,
                status=status.HTTP_200_OK,
            )

        # PUT: Admin updates placement
        self._admin_required(membership)
        serializer = StudentPlacementSerializer(data=request.data, context={"membership": membership})
        serializer.is_valid(raise_exception=True)
        unit_id = serializer.validated_data.get("academic_unit_id")

        old_unit = membership.academic_unit
        if unit_id is None:
            membership.academic_unit = None
            membership.save(update_fields=["academic_unit", "updated_at"])
            if old_unit:
                record_audit_event(
                    institution=membership.institution,
                    action=AuditAction.STUDENT_UNASSIGNED,
                    target_type="student_placement",
                    target_id=membership.id,
                    target_repr=f"{membership.user.email} removed from {old_unit.name}",
                    actor=request.user if isinstance(request.user, User) else None,
                    metadata={"previous_unit_id": str(old_unit.id), "previous_unit_code": old_unit.code},
                    request=request,
                )
        else:
            unit = AcademicUnit.objects.get(pk=unit_id)
            membership.academic_unit = unit
            membership.save(update_fields=["academic_unit", "updated_at"])
            record_audit_event(
                institution=membership.institution,
                action=AuditAction.STUDENT_PLACED,
                target_type="student_placement",
                target_id=membership.id,
                target_repr=f"{membership.user.email} placed in {unit.name} ({unit.code})",
                actor=request.user if isinstance(request.user, User) else None,
                metadata={"unit_id": str(unit.id), "unit_code": unit.code, "unit_name": unit.name},
                request=request,
            )

        out_serializer = MembershipSerializer(membership, context={"request": request})
        return Response(out_serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get", "post"], url_path="teaching-assignments")
    def teaching_assignments(self, request: Request, pk: str | None = None) -> Response:
        """List or create teaching assignments for a teacher."""
        membership = self.get_object()

        if request.method == "GET":
            is_self = isinstance(request.user, User) and membership.user_id == request.user.id
            is_admin = _is_institution_admin(request.user, membership.institution_id)
            if not (is_self or is_admin):
                raise PermissionDenied("You do not have permission to view these teaching assignments.")

            assignments = TeachingAssignment.objects.filter(
                membership=membership, status=TeachingAssignmentStatus.ACTIVE
            ).select_related("academic_unit", "membership__user")
            return Response(TeachingAssignmentSerializer(assignments, many=True).data, status=status.HTTP_200_OK)

        # POST: Admin assigns teacher
        self._admin_required(membership)
        if membership.role != MembershipRole.TEACHER:
            raise ValidationError({"membership": "Teaching assignments can only be created for members with role 'teacher'."})

        serializer = TeachingAssignmentSerializer(data=request.data, context={"membership": membership})
        serializer.is_valid(raise_exception=True)
        academic_unit_id = serializer.validated_data["academic_unit_id"]
        unit = AcademicUnit.objects.get(pk=academic_unit_id)
        subject = serializer.validated_data.get("subject", "").strip()

        assignment, created = TeachingAssignment.objects.update_or_create(
            membership=membership,
            academic_unit=unit,
            subject=subject,
            defaults={
                "institution": membership.institution,
                "status": TeachingAssignmentStatus.ACTIVE,
                "metadata": serializer.validated_data.get("metadata", {}),
            },
        )

        record_audit_event(
            institution=membership.institution,
            action=AuditAction.TEACHER_ASSIGNED,
            target_type="teaching_assignment",
            target_id=assignment.id,
            target_repr=f"{membership.user.email} -> {unit.name} ({subject or 'General'})",
            actor=request.user if isinstance(request.user, User) else None,
            metadata={
                "teacher_email": membership.user.email,
                "unit_id": str(unit.id),
                "unit_code": unit.code,
                "subject": subject,
            },
            request=request,
        )

        return Response(TeachingAssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED)


class TeachingAssignmentViewSet(viewsets.ModelViewSet):  # type: ignore[type-arg]
    """View set for managing specific teaching assignments directly."""

    serializer_class = TeachingAssignmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self) -> QuerySet[TeachingAssignment]:
        """Scope assignments to user's administrative institutions or own assignments."""
        user = self.request.user
        if not isinstance(user, User):
            return TeachingAssignment.objects.none()

        admin_inst_ids = Membership.objects.filter(
            user=user, role=MembershipRole.ADMINISTRATOR, status=MembershipStatus.ACTIVE
        ).values_list("institution_id", flat=True)

        return TeachingAssignment.objects.filter(
            models.Q(institution_id__in=admin_inst_ids) | models.Q(membership__user=user)
        ).select_related("academic_unit", "membership__user")

    def destroy(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Remove or deactivate a teaching assignment."""
        assignment = self.get_object()
        if not _is_institution_admin(request.user, assignment.institution_id):
            raise PermissionDenied("Only institution administrators may remove teaching assignments.")

        inst = assignment.institution
        repr_str = f"{assignment.membership.user.email} -> {assignment.academic_unit.name} ({assignment.subject or 'General'})"
        assignment_id = assignment.id

        assignment.delete()

        record_audit_event(
            institution=inst,
            action=AuditAction.TEACHER_UNASSIGNED,
            target_type="teaching_assignment",
            target_id=assignment_id,
            target_repr=repr_str,
            actor=request.user if isinstance(request.user, User) else None,
            metadata={"assignment_repr": repr_str},
            request=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
