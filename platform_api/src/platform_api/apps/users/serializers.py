"""Serializers for the users app."""

from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Serializer for reading user data."""

    class Meta:
        """Serializer metadata."""

        model = User
        fields = ["id", "email", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "email", "is_active", "created_at", "updated_at"]
