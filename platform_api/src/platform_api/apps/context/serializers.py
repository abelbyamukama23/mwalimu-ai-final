"""DRF serializers for Mwalimu context domain models."""

from __future__ import annotations

import uuid
from typing import Any

from rest_framework import serializers

from platform_api.apps.context.models import (
    ContextDomain,
    ContextResource,
    ContextScopeType,
    GeographicUnit,
    GeographicUnitStatus,
    InstitutionContextRegion,
    PedagogicalPurpose,
    UserFamiliarRegion,
    normalize_tags,
)

# ---------------------------------------------------------------------------
# GeographicUnit Serializers
# ---------------------------------------------------------------------------


class GeographicUnitSummarySerializer(serializers.ModelSerializer[GeographicUnit]):
    """Concise representation of a GeographicUnit."""

    class Meta:
        model = GeographicUnit
        fields = [
            "id",
            "name",
            "slug",
            "unit_type",
            "parent_id",
            "country_code",
            "status",
            "created_at",
        ]
        read_only_fields = fields


class GeographicUnitAncestorSerializer(serializers.Serializer[dict[str, Any]]):
    """Ancestor representation in a geographic hierarchy branch."""

    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.CharField()
    unit_type = serializers.CharField()


class GeographicUnitDetailSerializer(serializers.ModelSerializer[GeographicUnit]):
    """Detailed representation of a GeographicUnit including ancestor chain."""

    ancestors = serializers.SerializerMethodField()

    class Meta:
        model = GeographicUnit
        fields = [
            "id",
            "name",
            "slug",
            "unit_type",
            "parent_id",
            "country_code",
            "status",
            "metadata",
            "ancestors",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_ancestors(self, obj: GeographicUnit) -> list[dict[str, Any]]:
        """Return the upward ancestor chain ordered from root down to parent."""
        ancestors: list[dict[str, Any]] = []
        current = obj.parent
        visited: set[uuid.UUID] = {obj.id}
        while current is not None and current.id not in visited:
            ancestors.append(
                {
                    "id": current.id,
                    "name": current.name,
                    "slug": current.slug,
                    "unit_type": current.unit_type,
                }
            )
            visited.add(current.id)
            current = current.parent
        ancestors.reverse()
        return ancestors


# ---------------------------------------------------------------------------
# ContextDomain Serializer
# ---------------------------------------------------------------------------


class ContextDomainSerializer(serializers.ModelSerializer[ContextDomain]):
    """Serializer for ContextDomain classification."""

    class Meta:
        model = ContextDomain
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


# ---------------------------------------------------------------------------
# UserFamiliarRegion Serializers
# ---------------------------------------------------------------------------


class UserFamiliarRegionSerializer(serializers.ModelSerializer[UserFamiliarRegion]):
    """Serializer for user familiar region preferences."""

    geographic_unit = GeographicUnitSummarySerializer(read_only=True)
    geographic_unit_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = UserFamiliarRegion
        fields = [
            "id",
            "geographic_unit",
            "geographic_unit_id",
            "priority",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_geographic_unit_id(self, value: uuid.UUID) -> uuid.UUID:
        """Validate geographic unit exists and is active."""
        try:
            unit = GeographicUnit.objects.get(id=value)
        except GeographicUnit.DoesNotExist as err:
            raise serializers.ValidationError("Geographic unit not found.") from err
        if unit.status != GeographicUnitStatus.ACTIVE:
            raise serializers.ValidationError(
                "Cannot select an archived geographic unit as a familiar region."
            )
        return value


class UserFamiliarRegionReorderSerializer(serializers.Serializer[dict[str, Any]]):
    """Serializer for batch reordering user familiar regions."""

    region_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=True,
    )


# ---------------------------------------------------------------------------
# InstitutionContextRegion Serializers
# ---------------------------------------------------------------------------


class InstitutionContextRegionSerializer(
    serializers.ModelSerializer[InstitutionContextRegion]
):
    """Serializer for institution context region preferences."""

    geographic_unit = GeographicUnitSummarySerializer(read_only=True)
    geographic_unit_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = InstitutionContextRegion
        fields = [
            "id",
            "institution_id",
            "geographic_unit",
            "geographic_unit_id",
            "priority",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "institution_id", "created_at", "updated_at"]

    def validate_geographic_unit_id(self, value: uuid.UUID) -> uuid.UUID:
        """Validate geographic unit exists and is active."""
        try:
            unit = GeographicUnit.objects.get(id=value)
        except GeographicUnit.DoesNotExist as err:
            raise serializers.ValidationError("Geographic unit not found.") from err
        if unit.status != GeographicUnitStatus.ACTIVE:
            raise serializers.ValidationError(
                "Cannot select an archived geographic unit as an "
                "institution context region."
            )
        return value


class InstitutionContextRegionReorderSerializer(serializers.Serializer[dict[str, Any]]):
    """Serializer for batch reordering institution context regions."""

    region_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=True,
    )


# ---------------------------------------------------------------------------
# ContextResource Serializers
# ---------------------------------------------------------------------------


class ContextResourceSerializer(serializers.ModelSerializer[ContextResource]):
    """Serializer for ContextResource pedagogical knowledge snippets."""

    geographic_unit = GeographicUnitSummarySerializer(read_only=True)
    geographic_unit_id = serializers.UUIDField(write_only=True)
    context_domain = ContextDomainSerializer(read_only=True)
    context_domain_id = serializers.UUIDField(write_only=True)
    institution_id = serializers.UUIDField(
        required=False, allow_null=True, default=None
    )

    class Meta:
        model = ContextResource
        fields = [
            "id",
            "title",
            "content",
            "geographic_unit",
            "geographic_unit_id",
            "context_domain",
            "context_domain_id",
            "scope_type",
            "institution_id",
            "source_reference",
            "status",
            "applicable_subjects",
            "applicable_topics",
            "pedagogical_purposes",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_content(self, value: str) -> str:
        """Validate content length."""
        if len(value) > 5000:
            raise serializers.ValidationError("Content cannot exceed 5000 characters.")
        return value

    def validate_geographic_unit_id(self, value: uuid.UUID) -> uuid.UUID:
        """Validate geographic unit exists and is active."""
        try:
            unit = GeographicUnit.objects.get(id=value)
        except GeographicUnit.DoesNotExist as err:
            raise serializers.ValidationError("Geographic unit not found.") from err
        if unit.status != GeographicUnitStatus.ACTIVE:
            raise serializers.ValidationError(
                "Cannot attach context resources to an archived geographic unit."
            )
        return value

    def validate_context_domain_id(self, value: uuid.UUID) -> uuid.UUID:
        """Validate context domain exists."""
        if not ContextDomain.objects.filter(id=value).exists():
            raise serializers.ValidationError("Context domain not found.")
        return value

    def validate_applicable_subjects(self, value: Any) -> list[str]:
        """Normalize subject tags."""
        return normalize_tags(value)

    def validate_applicable_topics(self, value: Any) -> list[str]:
        """Normalize topic tags."""
        return normalize_tags(value)

    def validate_pedagogical_purposes(self, value: Any) -> list[str]:
        """Validate and normalize pedagogical purposes."""
        normalized = normalize_tags(value)
        valid = set(PedagogicalPurpose.values)
        for purpose in normalized:
            if purpose not in valid:
                raise serializers.ValidationError(
                    f"Invalid pedagogical purpose '{purpose}'. "
                    f"Valid choices: {sorted(valid)}."
                )
        return normalized

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Validate scope and institution alignment."""
        scope_type = attrs.get(
            "scope_type",
            self.instance.scope_type if self.instance else ContextScopeType.PLATFORM,
        )
        institution_id = attrs.get(
            "institution_id",
            self.instance.institution_id if self.instance else None,
        )

        if scope_type == ContextScopeType.PLATFORM and institution_id is not None:
            raise serializers.ValidationError(
                {
                    "institution_id": (
                        "Platform resources must not specify an institution."
                    )
                }
            )
        if scope_type == ContextScopeType.INSTITUTION and institution_id is None:
            raise serializers.ValidationError(
                {"institution_id": "Institution resources must specify an institution."}
            )
        return attrs
