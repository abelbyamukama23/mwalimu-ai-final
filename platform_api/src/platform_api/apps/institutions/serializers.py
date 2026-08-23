"""Serializers for the institutions app."""

from rest_framework import serializers

from .models import Institution


class InstitutionSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Serializer for institution data."""

    class Meta:
        """Serializer metadata."""

        model = Institution
        fields = ["id", "name", "slug", "status", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
