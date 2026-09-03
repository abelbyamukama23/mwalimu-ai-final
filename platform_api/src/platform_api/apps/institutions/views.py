"""Views for the institutions app."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db.models import Count, Q, QuerySet, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone
from rest_framework import permissions, status, viewsets
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
from .models import AuditAction, Institution, InstitutionalAuditEvent
from .serializers import InstitutionSerializer, InstitutionalAuditEventSerializer


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
                "prompt_tokens": row["prompt_tokens"],
                "completion_tokens": row["completion_tokens"],
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

