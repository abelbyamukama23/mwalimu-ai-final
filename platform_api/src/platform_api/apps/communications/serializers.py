"""Serializers for notifications and communication objects."""

from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Serializer for in-platform notifications."""

    actor_email = serializers.EmailField(
        source="actor.email", read_only=True, allow_null=True
    )
    actor_name = serializers.SerializerMethodField()

    class Meta:
        """Serializer metadata."""

        model = Notification
        fields = [
            "id",
            "actor_id",
            "actor_email",
            "actor_name",
            "notification_type",
            "title",
            "message",
            "payload",
            "is_read",
            "read_at",
            "expires_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_actor_name(self, obj: Notification) -> str | None:
        """Return display name of actor if available."""
        if not obj.actor:
            return None
        profile = getattr(obj.actor, "profile", None)
        if profile and profile.display_name:
            return profile.display_name
        return obj.actor.email
