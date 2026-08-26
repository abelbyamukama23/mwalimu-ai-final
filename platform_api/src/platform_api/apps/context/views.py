"""DRF views and viewsets for the Mwalimu context domain."""

from __future__ import annotations

import uuid
from typing import Any

from django.db import models
from django.db.models import QuerySet
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from platform_api.apps.context.models import (
    ContextResource,
    ContextResourceStatus,
    ContextScopeType,
    GeographicUnit,
    GeographicUnitStatus,
    InstitutionContextRegion,
    UserFamiliarRegion,
)
from platform_api.apps.context.permissions import (
    can_manage_context_resource,
    is_active_institution_member,
    is_institution_admin,
    is_platform_admin,
)
from platform_api.apps.context.serializers import (
    ContextResourceSerializer,
    GeographicUnitDetailSerializer,
    GeographicUnitSummarySerializer,
    InstitutionContextRegionReorderSerializer,
    InstitutionContextRegionSerializer,
    UserFamiliarRegionReorderSerializer,
    UserFamiliarRegionSerializer,
)
from platform_api.apps.context.services import (
    create_institution_context_region,
    create_user_familiar_region,
    reorder_institution_context_regions,
    reorder_user_familiar_regions,
)
from platform_api.apps.memberships.models import Membership, MembershipStatus
from platform_api.apps.users.models import User

# ---------------------------------------------------------------------------
# 1. GeographicUnit ViewSet
# ---------------------------------------------------------------------------


class GeographicUnitViewSet(viewsets.ReadOnlyModelViewSet):  # type: ignore[type-arg]
    """Read-only viewset for discovering GeographicUnit records."""

    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "pk"

    def get_serializer_class(self) -> type[BaseSerializer[Any]]:
        """Return detail serializer for retrieve, summary for list."""
        if self.action == "retrieve":
            return GeographicUnitDetailSerializer
        return GeographicUnitSummarySerializer

    def get_queryset(self) -> QuerySet[GeographicUnit]:
        """Return geographic units filtered by query parameters."""
        queryset = GeographicUnit.objects.all().select_related("parent")

        # Status filter: default to ACTIVE unless specified
        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)
        else:
            queryset = queryset.filter(status=GeographicUnitStatus.ACTIVE)

        # Parent filter
        parent_param = self.request.query_params.get("parent_id")
        if parent_param:
            if parent_param.lower() in ("null", "none", "root"):
                queryset = queryset.filter(parent__isnull=True)
            else:
                try:
                    parent_uuid = uuid.UUID(parent_param)
                    queryset = queryset.filter(parent_id=parent_uuid)
                except (ValueError, TypeError):
                    queryset = queryset.none()

        # Unit type filter
        unit_type = self.request.query_params.get("unit_type")
        if unit_type:
            queryset = queryset.filter(unit_type=unit_type)

        # Country code filter
        country_code = self.request.query_params.get("country_code")
        if country_code:
            queryset = queryset.filter(country_code__iexact=country_code)

        # Search query on name or slug
        query = self.request.query_params.get("query") or self.request.query_params.get(
            "search"
        )
        if query:
            queryset = queryset.filter(
                models.Q(name__icontains=query) | models.Q(slug__icontains=query)
            )

        return queryset.order_by("name")


# ---------------------------------------------------------------------------
# 2. UserFamiliarRegion ViewSet
# ---------------------------------------------------------------------------


class UserFamiliarRegionViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,  # type: ignore[type-arg]
):
    """Viewset for authenticated users to manage their familiar regions."""

    serializer_class = UserFamiliarRegionSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self) -> QuerySet[UserFamiliarRegion]:
        """Return familiar regions scoped to the authenticated user."""
        user = self.request.user
        if not isinstance(user, User):
            return UserFamiliarRegion.objects.none()
        return (
            UserFamiliarRegion.objects.filter(user=user)
            .select_related("geographic_unit")
            .order_by("priority", "-created_at")
        )

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Create a new familiar region preference for the authenticated user."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        if not isinstance(user, User):
            raise PermissionDenied("Authentication required.")

        region = create_user_familiar_region(
            user=user,
            geographic_unit_id=serializer.validated_data["geographic_unit_id"],
            priority=serializer.validated_data.get("priority"),
        )
        response_serializer = self.get_serializer(region)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["put"], url_path="reorder")
    def reorder(self, request: Request) -> Response:
        """Atomically reorder the authenticated user's familiar regions."""
        serializer = UserFamiliarRegionReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        if not isinstance(user, User):
            raise PermissionDenied("Authentication required.")

        updated_regions = reorder_user_familiar_regions(
            user=user,
            region_ids=serializer.validated_data["region_ids"],
        )
        response_serializer = self.get_serializer(updated_regions, many=True)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# 3. InstitutionContextRegion ViewSet
# ---------------------------------------------------------------------------


class InstitutionContextRegionViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,  # type: ignore[type-arg]
):
    """Viewset for managing institution context focus regions."""

    serializer_class = InstitutionContextRegionSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "pk"

    def _get_institution_id(self) -> uuid.UUID:
        """Extract institution_id from URL kwargs."""
        return uuid.UUID(str(self.kwargs["institution_id"]))

    def get_queryset(self) -> QuerySet[InstitutionContextRegion]:
        """Return context regions for the specified institution."""
        institution_id = self._get_institution_id()
        user = self.request.user

        # List access requires active membership in institution
        if not is_active_institution_member(user, institution_id):
            raise PermissionDenied(
                "You do not have permission to view context regions for "
                "this institution."
            )

        return (
            InstitutionContextRegion.objects.filter(institution_id=institution_id)
            .select_related("geographic_unit")
            .order_by("priority", "-created_at")
        )

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Create a new context region focus for the institution."""
        institution_id = self._get_institution_id()
        user = request.user

        if not is_institution_admin(user, institution_id):
            raise PermissionDenied(
                "You do not have permission to configure context regions for "
                "this institution."
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        region = create_institution_context_region(
            institution_id=institution_id,
            geographic_unit_id=serializer.validated_data["geographic_unit_id"],
            priority=serializer.validated_data.get("priority"),
        )
        response_serializer = self.get_serializer(region)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Delete an institution context region."""
        institution_id = self._get_institution_id()
        user = request.user

        if not is_institution_admin(user, institution_id):
            raise PermissionDenied(
                "You do not have permission to delete context regions for "
                "this institution."
            )

        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["put"], url_path="reorder")
    def reorder(self, request: Request, **kwargs: object) -> Response:
        """Atomically reorder the institution's context regions."""
        institution_id = self._get_institution_id()
        user = request.user

        if not is_institution_admin(user, institution_id):
            raise PermissionDenied(
                "You do not have permission to reorder context regions for "
                "this institution."
            )

        serializer = InstitutionContextRegionReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        updated_regions = reorder_institution_context_regions(
            institution_id=institution_id,
            region_ids=serializer.validated_data["region_ids"],
        )
        response_serializer = self.get_serializer(updated_regions, many=True)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# 4. ContextResource ViewSet
# ---------------------------------------------------------------------------


class ContextResourceViewSet(viewsets.ModelViewSet):  # type: ignore[type-arg]
    """Viewset for managing ContextResource knowledge snippets."""

    serializer_class = ContextResourceSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self) -> QuerySet[ContextResource]:
        """Return context resources visible to the user.

        Visibility rules:
        - Platform-scoped resources are visible to all authenticated users.
        - Institution-scoped resources are visible only to active members of
          that institution.
        - Platform admins can view all resources.
        """
        user = self.request.user
        if not isinstance(user, User):
            return ContextResource.objects.none()

        if is_platform_admin(user):
            queryset = ContextResource.objects.all()
        else:
            member_institution_ids = Membership.objects.filter(
                user=user,
                status=MembershipStatus.ACTIVE,
            ).values_list("institution_id", flat=True)

            queryset = ContextResource.objects.filter(
                models.Q(scope_type=ContextScopeType.PLATFORM)
                | models.Q(
                    scope_type=ContextScopeType.INSTITUTION,
                    institution_id__in=member_institution_ids,
                )
            )

        # Status filter: default to ACTIVE unless staff requests otherwise
        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)
        elif not is_platform_admin(user):
            queryset = queryset.filter(status=ContextResourceStatus.ACTIVE)

        # Filters
        geo_param = self.request.query_params.get(
            "geographic_unit_id"
        ) or self.request.query_params.get("geographic_unit")
        if geo_param:
            try:
                geo_uuid = uuid.UUID(geo_param)
                queryset = queryset.filter(geographic_unit_id=geo_uuid)
            except (ValueError, TypeError):
                queryset = queryset.none()

        domain_param = self.request.query_params.get(
            "context_domain_id"
        ) or self.request.query_params.get("context_domain")
        if domain_param:
            try:
                domain_uuid = uuid.UUID(domain_param)
                queryset = queryset.filter(context_domain_id=domain_uuid)
            except (ValueError, TypeError):
                queryset = queryset.none()

        scope_param = self.request.query_params.get("scope_type")
        if scope_param:
            queryset = queryset.filter(scope_type=scope_param)

        inst_param = self.request.query_params.get(
            "institution_id"
        ) or self.request.query_params.get("institution")
        if inst_param:
            try:
                inst_uuid = uuid.UUID(inst_param)
                queryset = queryset.filter(institution_id=inst_uuid)
            except (ValueError, TypeError):
                queryset = queryset.none()

        # Pedagogical tag filters (JSON containment)
        subj = self.request.query_params.get("applicable_subject")
        if subj:
            queryset = queryset.filter(
                applicable_subjects__contains=[subj.strip().lower()]
            )

        topic = self.request.query_params.get("applicable_topic")
        if topic:
            queryset = queryset.filter(
                applicable_topics__contains=[topic.strip().lower()]
            )

        purpose = self.request.query_params.get("pedagogical_purpose")
        if purpose:
            queryset = queryset.filter(
                pedagogical_purposes__contains=[purpose.strip().lower()]
            )

        # Full-text query on title, content, or source_reference
        query = self.request.query_params.get("query") or self.request.query_params.get(
            "search"
        )
        if query:
            queryset = queryset.filter(
                models.Q(title__icontains=query)
                | models.Q(content__icontains=query)
                | models.Q(source_reference__icontains=query)
            )

        return queryset.select_related(
            "geographic_unit", "context_domain", "institution"
        ).order_by("-created_at")

    def perform_create(self, serializer: BaseSerializer[Any]) -> None:
        """Create context resource after verifying authorization."""
        user = self.request.user
        validated_data = serializer.validated_data
        scope_type = validated_data.get("scope_type", ContextScopeType.PLATFORM)
        institution_id = validated_data.get("institution_id")

        if scope_type == ContextScopeType.PLATFORM and not is_platform_admin(user):
            raise PermissionDenied(
                "Only platform administrators may create platform context resources."
            )
        if scope_type == ContextScopeType.INSTITUTION and not is_institution_admin(
            user, institution_id
        ):
            raise PermissionDenied(
                "You do not have permission to create context resources for "
                "this institution."
            )

        serializer.save()

    def perform_update(self, serializer: BaseSerializer[Any]) -> None:
        """Update context resource after verifying management authorization."""
        user = self.request.user
        instance: ContextResource = serializer.instance  # type: ignore[assignment]
        if not can_manage_context_resource(user, instance):
            raise PermissionDenied(
                "You do not have permission to update this context resource."
            )
        serializer.save()

    def perform_destroy(self, instance: Any) -> None:
        """Delete context resource after verifying management authorization."""
        user = self.request.user
        if not isinstance(instance, ContextResource) or not can_manage_context_resource(
            user, instance
        ):
            raise PermissionDenied(
                "You do not have permission to delete this context resource."
            )
        instance.delete()
