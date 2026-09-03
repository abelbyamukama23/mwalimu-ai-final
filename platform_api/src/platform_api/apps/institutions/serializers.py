"""Serializers for the institutions app."""

from rest_framework import serializers

from .models import Institution, InstitutionType


class InstitutionSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Serializer for institution data."""

    institution_type = serializers.ChoiceField(
        choices=InstitutionType.choices,
        default=InstitutionType.SCHOOL,
        required=False,
    )
    created_by_id = serializers.UUIDField(source="created_by.id", read_only=True)

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
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by_id", "created_at", "updated_at"]
