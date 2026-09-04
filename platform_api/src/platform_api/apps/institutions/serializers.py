"""Serializers for the institutions app."""

from typing import Any

from rest_framework import serializers

from .models import Institution, InstitutionType, InstitutionalAuditEvent


class InstitutionSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Serializer for institution data."""

    institution_type = serializers.ChoiceField(
        choices=InstitutionType.choices,
        default=InstitutionType.SCHOOL,
        required=False,
    )
    created_by_id = serializers.UUIDField(source="created_by.id", read_only=True)
    badge_url = serializers.SerializerMethodField()

    class Meta:
        """Serializer metadata."""

        model = Institution
        fields = [
            "id",
            "name",
            "slug",
            "status",
            "institution_type",
            "created_by_id",
            "badge_url",
            "logo_updated_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_by_id",
            "badge_url",
            "logo_updated_at",
            "created_at",
            "updated_at",
        ]

    def get_badge_url(self, obj: Institution) -> str | None:
        """Return safe URL for institutional badge/logo if present."""
        if not obj.logo_object_key:
            return None
        request = self.context.get("request")
        path = f"/api/v1/institutions/{obj.id}/badge/"
        if request:
            return request.build_absolute_uri(path)  # type: ignore[no-any-return]
        return path


class InstitutionalAuditEventSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Serializer for institutional audit ledger events."""

    actor_email = serializers.EmailField(
        source="actor.email", read_only=True, allow_null=True
    )

    class Meta:
        """Serializer metadata."""

        model = InstitutionalAuditEvent
        fields = [
            "id",
            "institution_id",
            "actor_id",
            "actor_email",
            "action",
            "target_type",
            "target_id",
            "target_repr",
            "metadata",
            "ip_address",
            "created_at",
        ]
        read_only_fields = fields


class AcademicUnitSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Serializer for academic units within an institution."""

    institution_id = serializers.UUIDField(source="institution.id", read_only=True)
    student_count = serializers.SerializerMethodField()
    teacher_count = serializers.SerializerMethodField()

    class Meta:
        """Serializer metadata."""

        from .models import AcademicUnit

        model = AcademicUnit
        fields = [
            "id",
            "institution_id",
            "name",
            "code",
            "unit_type",
            "order",
            "is_active",
            "metadata",
            "student_count",
            "teacher_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "institution_id",
            "student_count",
            "teacher_count",
            "created_at",
            "updated_at",
        ]

    def get_student_count(self, obj: Any) -> int:
        """Return count of active students placed in this academic unit."""
        return obj.student_memberships.filter(status="active").count()

    def get_teacher_count(self, obj: Any) -> int:
        """Return count of active teachers assigned to this academic unit."""
        return obj.teaching_assignments.filter(status="active").count()


class AcademicUnitPresetSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """Input serializer for applying standard academic structure presets."""

    PRESET_CHOICES = [
        ("primary", "Primary (P1 - P7)"),
        ("secondary", "Secondary (S1 - S6)"),
        ("primary_and_secondary", "Primary & Secondary (P1 - S6)"),
        ("tertiary", "Tertiary / Higher Ed (Year 1 - Year 4)"),
    ]
    preset = serializers.ChoiceField(choices=PRESET_CHOICES)

