"""Serializers for the institutions app."""

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

