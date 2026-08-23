"""Serializers for the resources app."""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from platform_api.apps.libraries.models import Library

from .models import Resource, ResourceStatus, ResourceType

User = get_user_model()


class ResourceLibrarySerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Minimal library representation nested inside resource responses."""

    class Meta:
        """Serializer metadata."""

        model = Library
        fields = ["id", "name", "slug"]


class ResourceUserSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Minimal user representation nested inside resource responses."""

    class Meta:
        """Serializer metadata."""

        model = User
        fields = ["id", "email"]


class ResourceSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Serializer for resource metadata."""

    library = ResourceLibrarySerializer(read_only=True)
    created_by = ResourceUserSerializer(read_only=True)
    resource_type = serializers.ChoiceField(choices=ResourceType.choices)
    status = serializers.ChoiceField(
        choices=ResourceStatus.choices,
        required=False,
        read_only=True,
    )

    class Meta:
        """Serializer metadata."""

        model = Resource
        fields = [
            "id",
            "library",
            "name",
            "resource_type",
            "original_filename",
            "content_type",
            "size",
            "object_key",
            "checksum",
            "status",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "library",
            "created_by",
            "original_filename",
            "content_type",
            "size",
            "object_key",
            "checksum",
            "status",
            "created_at",
            "updated_at",
        ]

    def validate_resource_type(self, value: str) -> str:
        """Ensure the resource type is supported."""
        if value not in ResourceType.values:
            raise serializers.ValidationError(
                f"Unsupported resource type: {value}.",
            )
        return value
