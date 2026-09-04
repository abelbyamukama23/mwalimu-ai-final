"""Views for the institutions app."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db.models import Count, Q, QuerySet, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone
from rest_framework import parsers, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from platform_api.apps.agents.models import AgentRunRecord, AgentRunStatus
from platform_api.apps.connectors.models import (
    Connection,
    ConnectionStatus,
    ConnectionSyncJob,
    SyncJobStatus,
)
from platform_api.apps.connectors.serializers import ConnectionListSerializer
from platform_api.apps.libraries.models import Library, LibraryStatus, LibraryVisibility
from platform_api.apps.memberships.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
)
from platform_api.apps.processing.models import ProcessingRun, ProcessingStatus
from platform_api.apps.resources.models import Resource
from platform_api.apps.users.models import User

from .audit import record_audit_event
from .models import (
    AcademicUnit,
    AcademicUnitType,
    AuditAction,
    Institution,
    InstitutionalAuditEvent,
)
from .serializers import (
    AcademicUnitPresetSerializer,
    AcademicUnitSerializer,
    InstitutionSerializer,
    InstitutionalAuditEventSerializer,
)


def _is_institution_admin(user: User | Any, institution: Institution) -> bool:
    """Return True if the user is an active administrator of the institution."""
    if not isinstance(user, User):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    return Membership.objects.filter(
        user=user,
        institution=institution,
        role=MembershipRole.ADMINISTRATOR,
        status=MembershipStatus.ACTIVE,
    ).exists()


def _is_institution_member(user: User | Any, institution: Institution) -> bool:
    """Return True if the user has an active membership in the institution."""
    if not isinstance(user, User):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    return Membership.objects.filter(
        user=user,
        institution=institution,
        status=MembershipStatus.ACTIVE,
    ).exists()


class InstitutionViewSet(viewsets.ModelViewSet):  # type: ignore[type-arg]
    """View set for institution management.

    Any authenticated user may discover institutions. Any authenticated user may
    create an institution and become its first administrator. Only institution
    administrators may update, delete, view usage, or view audit logs.
    """

    serializer_class = InstitutionSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self) -> QuerySet[Institution]:
        """Return all institutions ordered by creation date."""
        return Institution.objects.all().order_by("-created_at")

    def perform_create(self, serializer: BaseSerializer[Any]) -> None:
        """Create the institution and atomically make the requester its first admin."""
        user = self.request.user
        created_by_user = user if isinstance(user, User) else None
        from django.db import transaction

        with transaction.atomic():
            institution = serializer.save(created_by=created_by_user)
            if isinstance(user, User):
                Membership.objects.create(
                    user=user,
                    institution=institution,
                    role=MembershipRole.ADMINISTRATOR,
                    status=MembershipStatus.ACTIVE,
                )
                record_audit_event(
                    institution=institution,
                    action=AuditAction.INSTITUTION_UPDATED,
                    target_type="institution",
                    target_id=institution.id,
                    target_repr=institution.name,
                    actor=user,
                    metadata={"event": "created", "name": institution.name},
                    request=self.request,
                )

    def update(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Only institution administrators may update an institution."""
        institution = self.get_object()
        if not _is_institution_admin(request.user, institution):
            raise PermissionDenied(
                "You do not have permission to update this institution.",
            )
        response = super().update(request, *args, **kwargs)
        record_audit_event(
            institution=institution,
            action=AuditAction.INSTITUTION_UPDATED,
            target_type="institution",
            target_id=institution.id,
            target_repr=institution.name,
            actor=request.user if isinstance(request.user, User) else None,
            metadata={"updated_fields": list(request.data.keys())},
            request=request,
        )
        return response

    def partial_update(
        self, request: Request, *args: object, **kwargs: object
    ) -> Response:
        """Only institution administrators may partially update an institution."""
        institution = self.get_object()
        if not _is_institution_admin(request.user, institution):
            raise PermissionDenied(
                "You do not have permission to update this institution.",
            )
        response = super().partial_update(request, *args, **kwargs)
        record_audit_event(
            institution=institution,
            action=AuditAction.INSTITUTION_UPDATED,
            target_type="institution",
            target_id=institution.id,
            target_repr=institution.name,
            actor=request.user if isinstance(request.user, User) else None,
            metadata={"updated_fields": list(request.data.keys())},
            request=request,
        )
        return response

    def destroy(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Only institution administrators may delete an institution."""
        institution = self.get_object()
        if not _is_institution_admin(request.user, institution):
            raise PermissionDenied(
                "You do not have permission to delete this institution.",
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["get"], url_path="overview")
    def overview(self, request: Request, pk: str | None = None) -> Response:
        """Consolidated operational intelligence for an institution."""
        institution = self.get_object()
        if not _is_institution_admin(request.user, institution):
            raise PermissionDenied(
                "You do not have permission to view overview metrics for this institution."
            )

        # 1. Members
        active_members_qs = Membership.objects.filter(
            institution=institution, status=MembershipStatus.ACTIVE
        )
        total_active_members = active_members_qs.count()
        pending_members = Membership.objects.filter(
            institution=institution, status=MembershipStatus.PENDING
        ).count()
        role_counts: dict[str, int] = {r: 0 for r in MembershipRole.values}
        for item in active_members_qs.values("role").annotate(c=Count("id")):
            role_counts[item["role"]] = item["c"]

        # 2. Knowledge
        libraries_qs = Library.objects.filter(
            institution=institution, status=LibraryStatus.ACTIVE
        )
        total_libraries = libraries_qs.count()
        discoverable_libraries = libraries_qs.filter(
            visibility=LibraryVisibility.DISCOVERABLE
        ).count()
        restricted_libraries = libraries_qs.filter(
            visibility=LibraryVisibility.RESTRICTED
        ).count()

        resources_qs = Resource.objects.filter(library__institution=institution)
        total_resources = resources_qs.count()
        resources_by_status: dict[str, int] = {}
        for item in resources_qs.values("status").annotate(c=Count("id")):
            resources_by_status[item["status"]] = item["c"]

        # 3. Integrations
        connections_qs = Connection.objects.filter(library__institution=institution)
        total_connections = connections_qs.count()
        active_connections = connections_qs.filter(
            status=ConnectionStatus.ACTIVE
        ).count()
        error_connections = connections_qs.filter(
            status=ConnectionStatus.ERROR
        ).count()

        # 4. AI Telemetry (30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        ai_agg = AgentRunRecord.objects.filter(
            session__institution=institution,
            created_at__gte=thirty_days_ago,
        ).aggregate(
            total_tokens=Coalesce(Sum("total_tokens"), 0),
            total_runs=Count("id"),
            active_users=Count("user", distinct=True),
        )

        # 5. Operational Health
        two_hours_ago = timezone.now() - timedelta(hours=2)
        stuck_processing = ProcessingRun.objects.filter(
            library__institution=institution,
            status=ProcessingStatus.PROCESSING,
            created_at__lt=two_hours_ago,
        ).count()
        failed_ingestion = ProcessingRun.objects.filter(
            library__institution=institution,
            status=ProcessingStatus.FAILED,
        ).count()
        failed_sync = ConnectionSyncJob.objects.filter(
            connection__library__institution=institution,
            status=SyncJobStatus.FAILED,
        ).count()

        health_status = "healthy"
        if stuck_processing > 0 or failed_ingestion > 0 or failed_sync > 0 or error_connections > 0:
            health_status = "attention_needed"

        # 6. Recent Activity
        recent_events = (
            InstitutionalAuditEvent.objects.filter(institution=institution)
            .select_related("actor")
            .order_by("-created_at")[:5]
        )
        recent_activity_data = InstitutionalAuditEventSerializer(
            recent_events, many=True
        ).data

        payload = {
            "institution_id": str(institution.id),
            "name": institution.name,
            "slug": institution.slug,
            "institution_type": institution.institution_type,
            "status": institution.status,
            "members": {
                "total_active": total_active_members,
                "pending": pending_members,
                "by_role": role_counts,
            },
            "knowledge": {
                "total_libraries": total_libraries,
                "discoverable_libraries": discoverable_libraries,
                "restricted_libraries": restricted_libraries,
                "total_resources": total_resources,
                "resources_by_status": resources_by_status,
            },
            "integrations": {
                "total_connections": total_connections,
                "active_connections": active_connections,
                "error_connections": error_connections,
            },
            "ai_telemetry_30d": {
                "total_tokens": ai_agg["total_tokens"],
                "total_credits": max(0, round(ai_agg["total_tokens"] / 1000)),
                "total_runs": ai_agg["total_runs"],
                "active_users": ai_agg["active_users"],
            },
            "health": {
                "status": health_status,
                "stuck_processing_count": stuck_processing,
                "failed_ingestion_count": failed_ingestion,
                "failed_sync_count": failed_sync,
            },
            "recent_activity": recent_activity_data,
        }
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="usage")
    def usage(self, request: Request, pk: str | None = None) -> Response:
        """AI token consumption and agent run telemetry for the institution."""
        institution = self.get_object()
        if not _is_institution_admin(request.user, institution):
            raise PermissionDenied(
                "You do not have permission to view AI usage metrics for this institution."
            )

        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")
        now = timezone.now()

        if start_date_str:
            try:
                start_dt = timezone.datetime.fromisoformat(start_date_str).replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                start_dt = now - timedelta(days=30)
        else:
            start_dt = now - timedelta(days=30)

        if end_date_str:
            try:
                end_dt = timezone.datetime.fromisoformat(end_date_str).replace(
                    hour=23, minute=59, second=59, tzinfo=timezone.utc
                )
            except ValueError:
                end_dt = now
        else:
            end_dt = now

        runs_qs = AgentRunRecord.objects.filter(
            session__institution=institution,
            created_at__gte=start_dt,
            created_at__lte=end_dt,
        )

        summary_agg = runs_qs.aggregate(
            total_tokens=Coalesce(Sum("total_tokens"), 0),
            prompt_tokens=Coalesce(Sum("prompt_tokens"), 0),
            completion_tokens=Coalesce(Sum("completion_tokens"), 0),
            total_runs=Count("id"),
            completed_runs=Count("id", filter=Q(status=AgentRunStatus.COMPLETED)),
            failed_runs=Count("id", filter=Q(status=AgentRunStatus.FAILED)),
            cancelled_runs=Count("id", filter=Q(status=AgentRunStatus.CANCELLED)),
            timed_out_runs=Count("id", filter=Q(status=AgentRunStatus.TIMED_OUT)),
            active_users=Count("user", distinct=True),
        )

        summary_agg["total_credits"] = max(0, round(summary_agg["total_tokens"] / 1000))
        summary_agg["query_credits"] = max(0, round(summary_agg["prompt_tokens"] / 1000))
        summary_agg["synthesis_credits"] = max(0, round(summary_agg["completion_tokens"] / 1000))

        timeline_qs = (
            runs_qs.annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(
                total_tokens=Coalesce(Sum("total_tokens"), 0),
                prompt_tokens=Coalesce(Sum("prompt_tokens"), 0),
                completion_tokens=Coalesce(Sum("completion_tokens"), 0),
                total_runs=Count("id"),
            )
            .order_by("date")
        )
        timeline = [
            {
                "date": row["date"].isoformat(),
                "total_tokens": row["total_tokens"],
                "total_credits": max(0, round(row["total_tokens"] / 1000)),
                "prompt_tokens": row["prompt_tokens"],
                "query_credits": max(0, round(row["prompt_tokens"] / 1000)),
                "completion_tokens": row["completion_tokens"],
                "synthesis_credits": max(0, round(row["completion_tokens"] / 1000)),
                "total_runs": row["total_runs"],
            }
            for row in timeline_qs
        ]

        top_users_qs = (
            runs_qs.values("user__id", "user__email")
            .annotate(
                total_tokens=Coalesce(Sum("total_tokens"), 0),
                total_runs=Count("id"),
            )
            .order_by("-total_tokens")[:10]
        )
        top_users = [
            {
                "user_id": str(row["user__id"]),
                "email": row["user__email"] or "Unknown",
                "total_tokens": row["total_tokens"],
                "total_credits": max(0, round(row["total_tokens"] / 1000)),
                "total_runs": row["total_runs"],
            }
            for row in top_users_qs
        ]

        payload = {
            "institution_id": str(institution.id),
            "start_date": start_dt.date().isoformat(),
            "end_date": end_dt.date().isoformat(),
            "summary": summary_agg,
            "timeline": timeline,
            "top_users": top_users,
        }
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="audit-logs")
    def audit_logs(self, request: Request, pk: str | None = None) -> Response:
        """Immutable administrative audit ledger for an institution."""
        institution = self.get_object()
        if not _is_institution_admin(request.user, institution):
            raise PermissionDenied(
                "You do not have permission to view audit logs for this institution."
            )

        qs = (
            InstitutionalAuditEvent.objects.filter(institution=institution)
            .select_related("actor")
            .order_by("-created_at")
        )

        action_filter = request.query_params.get("action")
        if action_filter:
            qs = qs.filter(action=action_filter)

        target_type_filter = request.query_params.get("target_type")
        if target_type_filter:
            qs = qs.filter(target_type=target_type_filter)

        search_query = request.query_params.get("search")
        if search_query:
            qs = qs.filter(
                Q(target_repr__icontains=search_query)
                | Q(actor__email__icontains=search_query)
            )

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = InstitutionalAuditEventSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = InstitutionalAuditEventSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="connections")
    def connections(self, request: Request, pk: str | None = None) -> Response:
        """List all external knowledge connections configured across this institution."""
        institution = self.get_object()
        if not _is_institution_admin(request.user, institution):
            raise PermissionDenied(
                "You do not have permission to view connections for this institution."
            )

        connections = Connection.objects.filter(
            library__institution=institution
        ).select_related("connector", "library").order_by("-created_at")

        serializer = ConnectionListSerializer(connections, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["post", "delete"],
        url_path="branding",
        parser_classes=[parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser],
    )
    def branding(self, request: Request, pk: str | None = None) -> Response:
        """Upload, replace, or remove the institutional badge/logo."""
        import os
        import uuid
        from django.core.exceptions import ValidationError
        from rest_framework.exceptions import ValidationError as DRFValidationError
        from platform_api.apps.resources.storage import get_object_storage

        institution = self.get_object()
        if not _is_institution_admin(request.user, institution):
            raise PermissionDenied(
                "Only institution administrators may modify institutional branding."
            )

        storage = get_object_storage()

        if request.method == "DELETE":
            if institution.logo_object_key:
                try:
                    storage.delete(institution.logo_object_key)
                except Exception:  # noqa: BLE001
                    pass
                institution.logo_object_key = ""
                institution.logo_content_type = ""
                institution.logo_updated_at = timezone.now()
                institution.save(
                    update_fields=[
                        "logo_object_key",
                        "logo_content_type",
                        "logo_updated_at",
                    ]
                )
                record_audit_event(
                    institution=institution,
                    action=AuditAction.BRANDING_UPDATED,
                    target_type="institution",
                    target_id=institution.id,
                    target_repr=institution.name,
                    actor=request.user if isinstance(request.user, User) else None,
                    metadata={"event": "badge_removed"},
                    request=request,
                )
            return Response(status=status.HTTP_204_NO_CONTENT)

        # POST: Upload or replace
        uploaded_file = request.FILES.get("file") or request.FILES.get("logo")
        if not uploaded_file:
            raise DRFValidationError({"file": "No image file provided for institutional badge."})

        allowed_types = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/webp": ".webp",
            "image/svg+xml": ".svg",
        }
        content_type = str(uploaded_file.content_type).lower()
        if content_type not in allowed_types:
            raise DRFValidationError(
                {"file": f"Unsupported image type: '{content_type}'. Allowed: PNG, JPEG, WebP, SVG."}
            )

        max_size = 2 * 1024 * 1024  # 2MB
        if uploaded_file.size > max_size:
            raise DRFValidationError(
                {"file": f"File size exceeds 2MB limit (received {uploaded_file.size} bytes)."}
            )

        data = uploaded_file.read()
        ext = allowed_types[content_type]
        new_key = f"institutions/{institution.id}/branding/{uuid.uuid4().hex}{ext}"

        from io import BytesIO

        try:
            storage.upload(
                new_key,
                BytesIO(data),
                content_type=content_type,
                size=len(data),
            )
        except Exception as exc:
            raise DRFValidationError({"file": f"Storage upload failed: {exc}"}) from exc

        # Clean up old stored logo if exists
        old_key = institution.logo_object_key
        if old_key and old_key != new_key:
            try:
                storage.delete(old_key)
            except Exception:  # noqa: BLE001
                pass

        institution.logo_object_key = new_key
        institution.logo_content_type = content_type
        institution.logo_updated_at = timezone.now()
        institution.save(
            update_fields=[
                "logo_object_key",
                "logo_content_type",
                "logo_updated_at",
            ]
        )

        record_audit_event(
            institution=institution,
            action=AuditAction.BRANDING_UPDATED,
            target_type="institution",
            target_id=institution.id,
            target_repr=institution.name,
            actor=request.user if isinstance(request.user, User) else None,
            metadata={
                "event": "badge_uploaded",
                "content_type": content_type,
                "size": len(data),
            },
            request=request,
        )

        serializer = self.get_serializer(institution)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["get"],
        url_path="badge",
        permission_classes=[permissions.AllowAny],
    )
    def badge(self, request: Request, pk: str | None = None) -> Any:
        """Stream the institution's official badge/logo."""
        from django.http import FileResponse, Http404
        from platform_api.apps.resources.storage import get_object_storage

        institution = self.get_object()
        if not institution.logo_object_key:
            raise Http404("Institution has not uploaded a badge logo.")

        storage = get_object_storage()
        try:
            stream = storage.download(institution.logo_object_key)
        except Exception as exc:
            raise Http404(f"Badge object not found in storage: {exc}") from exc

        response = FileResponse(stream, content_type=institution.logo_content_type or "image/png")
        response["Cache-Control"] = "public, max-age=3600"
        return response


class AcademicUnitViewSet(viewsets.ModelViewSet):  # type: ignore[type-arg]
    """View set for managing academic structure (grades, classes, departments) in an institution.

    Members may view academic units. Only institution administrators may create,
    update, delete, or apply structure presets.
    """

    serializer_class = AcademicUnitSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "pk"

    def _get_institution(self) -> Institution:
        """Resolve target institution from URL kwargs or query parameters."""
        inst_id = self.kwargs.get("institution_pk") or self.request.query_params.get("institution_id")
        if not inst_id:
            raise PermissionDenied("Institution context is required.")
        try:
            return Institution.objects.get(pk=inst_id)
        except Institution.DoesNotExist:
            raise PermissionDenied("Institution not found.")

    def get_queryset(self) -> QuerySet[AcademicUnit]:
        """Return academic units for the institution if user is an authorized member."""
        institution = self._get_institution()
        if not _is_institution_member(self.request.user, institution):
            raise PermissionDenied("You must be an active member of this institution to view its academic structure.")
        return AcademicUnit.objects.filter(institution=institution).order_by("order", "name")

    def perform_create(self, serializer: BaseSerializer[Any]) -> None:
        """Create academic unit and record audit log."""
        institution = self._get_institution()
        if not _is_institution_admin(self.request.user, institution):
            raise PermissionDenied("Only institution administrators may create academic units.")
        unit: AcademicUnit = serializer.save(institution=institution)
        record_audit_event(
            institution=institution,
            action=AuditAction.ACADEMIC_UNIT_CREATED,
            target_type="academic_unit",
            target_id=unit.id,
            target_repr=f"{unit.name} ({unit.code})",
            actor=self.request.user if isinstance(self.request.user, User) else None,
            metadata={"name": unit.name, "code": unit.code, "unit_type": unit.unit_type},
            request=self.request,
        )

    def perform_update(self, serializer: BaseSerializer[Any]) -> None:
        """Update academic unit and record audit log."""
        institution = self._get_institution()
        if not _is_institution_admin(self.request.user, institution):
            raise PermissionDenied("Only institution administrators may modify academic units.")
        unit = self.get_object()
        old_active = unit.is_active
        updated_unit: AcademicUnit = serializer.save()
        
        action = AuditAction.ACADEMIC_UNIT_UPDATED
        if old_active and not updated_unit.is_active:
            action = AuditAction.ACADEMIC_UNIT_DEACTIVATED

        record_audit_event(
            institution=institution,
            action=action,
            target_type="academic_unit",
            target_id=updated_unit.id,
            target_repr=f"{updated_unit.name} ({updated_unit.code})",
            actor=self.request.user if isinstance(self.request.user, User) else None,
            metadata={"updated_fields": list(self.request.data.keys())},
            request=self.request,
        )

    def perform_destroy(self, instance: AcademicUnit) -> None:
        """Delete academic unit and record audit log."""
        institution = self._get_institution()
        if not _is_institution_admin(self.request.user, institution):
            raise PermissionDenied("Only institution administrators may delete academic units.")
        unit_repr = f"{instance.name} ({instance.code})"
        unit_id = instance.id
        instance.delete()
        record_audit_event(
            institution=institution,
            action=AuditAction.ACADEMIC_UNIT_DELETED,
            target_type="academic_unit",
            target_id=unit_id,
            target_repr=unit_repr,
            actor=self.request.user if isinstance(self.request.user, User) else None,
            metadata={"deleted_unit": unit_repr},
            request=self.request,
        )

    @action(detail=False, methods=["post"], url_path="apply-preset")
    def apply_preset(self, request: Request, institution_pk: str | None = None) -> Response:
        """Apply a standard academic structure preset to the institution."""
        institution = self._get_institution()
        if not _is_institution_admin(request.user, institution):
            raise PermissionDenied("Only institution administrators may apply structure presets.")

        serializer = AcademicUnitPresetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        preset_choice = serializer.validated_data["preset"]

        presets_map: dict[str, list[tuple[str, str, str, int]]] = {
            "primary": [
                ("Primary 1", "P1", AcademicUnitType.GRADE, 1),
                ("Primary 2", "P2", AcademicUnitType.GRADE, 2),
                ("Primary 3", "P3", AcademicUnitType.GRADE, 3),
                ("Primary 4", "P4", AcademicUnitType.GRADE, 4),
                ("Primary 5", "P5", AcademicUnitType.GRADE, 5),
                ("Primary 6", "P6", AcademicUnitType.GRADE, 6),
                ("Primary 7", "P7", AcademicUnitType.GRADE, 7),
            ],
            "secondary": [
                ("Senior 1", "S1", AcademicUnitType.YEAR, 1),
                ("Senior 2", "S2", AcademicUnitType.YEAR, 2),
                ("Senior 3", "S3", AcademicUnitType.YEAR, 3),
                ("Senior 4", "S4", AcademicUnitType.YEAR, 4),
                ("Senior 5", "S5", AcademicUnitType.YEAR, 5),
                ("Senior 6", "S6", AcademicUnitType.YEAR, 6),
            ],
            "primary_and_secondary": [
                ("Primary 1", "P1", AcademicUnitType.GRADE, 1),
                ("Primary 2", "P2", AcademicUnitType.GRADE, 2),
                ("Primary 3", "P3", AcademicUnitType.GRADE, 3),
                ("Primary 4", "P4", AcademicUnitType.GRADE, 4),
                ("Primary 5", "P5", AcademicUnitType.GRADE, 5),
                ("Primary 6", "P6", AcademicUnitType.GRADE, 6),
                ("Primary 7", "P7", AcademicUnitType.GRADE, 7),
                ("Senior 1", "S1", AcademicUnitType.YEAR, 8),
                ("Senior 2", "S2", AcademicUnitType.YEAR, 9),
                ("Senior 3", "S3", AcademicUnitType.YEAR, 10),
                ("Senior 4", "S4", AcademicUnitType.YEAR, 11),
                ("Senior 5", "S5", AcademicUnitType.YEAR, 12),
                ("Senior 6", "S6", AcademicUnitType.YEAR, 13),
            ],
            "tertiary": [
                ("Year 1", "Y1", AcademicUnitType.YEAR, 1),
                ("Year 2", "Y2", AcademicUnitType.YEAR, 2),
                ("Year 3", "Y3", AcademicUnitType.YEAR, 3),
                ("Year 4", "Y4", AcademicUnitType.YEAR, 4),
            ],
        }

        unit_specs = presets_map[preset_choice]
        created_or_updated: list[AcademicUnit] = []
        for name, code, u_type, order in unit_specs:
            unit, _ = AcademicUnit.objects.update_or_create(
                institution=institution,
                code=code,
                defaults={
                    "name": name,
                    "unit_type": u_type,
                    "order": order,
                    "is_active": True,
                },
            )
            created_or_updated.append(unit)

        record_audit_event(
            institution=institution,
            action=AuditAction.ACADEMIC_UNIT_CREATED,
            target_type="academic_structure",
            target_id=institution.id,
            target_repr=f"Preset: {preset_choice}",
            actor=request.user if isinstance(request.user, User) else None,
            metadata={"preset": preset_choice, "units_count": len(created_or_updated)},
            request=request,
        )

        out_serializer = AcademicUnitSerializer(created_or_updated, many=True)
        return Response(out_serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="teachers")
    def teachers(self, request: Request, pk: str | None = None, institution_pk: str | None = None) -> Response:
        """List active teachers assigned to this academic unit."""
        unit = self.get_object()
        from platform_api.apps.memberships.serializers import TeachingAssignmentSerializer

        assignments = unit.teaching_assignments.filter(status="active").select_related("membership__user", "academic_unit")
        serializer = TeachingAssignmentSerializer(assignments, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="students")
    def students(self, request: Request, pk: str | None = None, institution_pk: str | None = None) -> Response:
        """List active students placed in this academic unit."""
        unit = self.get_object()
        from platform_api.apps.memberships.serializers import MembershipSerializer

        students = unit.student_memberships.filter(status=MembershipStatus.ACTIVE).select_related("user", "institution")
        serializer = MembershipSerializer(students, many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


