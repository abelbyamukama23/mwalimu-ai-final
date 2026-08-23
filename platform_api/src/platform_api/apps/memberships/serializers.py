"""Serializers for the memberships app."""

import uuid

from django.contrib.auth import get_user_model
from rest_framework import serializers

from platform_api.apps.institutions.models import Institution

from .models import Membership, MembershipRole, MembershipStatus

User = get_user_model()


class MembershipUserSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Minimal user representation nested inside membership responses."""

    class Meta:
        """Serializer metadata."""

        model = User
        fields = ["id", "email"]


class MembershipInstitutionSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Minimal institution representation nested inside membership responses."""

    class Meta:
        """Serializer metadata."""

        model = Institution
        fields = ["id", "name", "slug"]


class MembershipSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Serializer for membership data."""

    user = MembershipUserSerializer(read_only=True)
    institution = MembershipInstitutionSerializer(read_only=True)
    institution_id = serializers.UUIDField(write_only=True)
    role = serializers.ChoiceField(choices=MembershipRole.choices, required=False)
    status = serializers.ChoiceField(choices=MembershipStatus.choices, required=False)

    class Meta:
        """Serializer metadata."""

        model = Membership
        fields = [
            "id",
            "user",
            "institution",
            "institution_id",
            "role",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user", "institution", "created_at", "updated_at"]

    def validate_institution_id(self, value: uuid.UUID) -> uuid.UUID:
        """Ensure the referenced institution exists."""
        institution_id = value
        if not Institution.objects.filter(pk=institution_id).exists():
            raise serializers.ValidationError("Institution not found.")
        return institution_id

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        """Apply domain-level membership validation on creation."""
        if self.instance is not None:
            return attrs

        request = self.context.get("request")
        user = request.user if request else None
        raw_institution_id = attrs.get("institution_id")
        if user and raw_institution_id:
            institution_id = uuid.UUID(str(raw_institution_id))
            existing = Membership.objects.filter(
                user=user,
                institution_id=institution_id,
                status__in=(MembershipStatus.ACTIVE, MembershipStatus.PENDING),
            ).exists()
            if existing:
                message = (
                    "You already have an active or pending membership "
                    "for this institution."
                )
                raise serializers.ValidationError({"institution_id": message})

        return attrs

    def create(self, validated_data: dict[str, object]) -> Membership:
        """Create a self-requested student membership for the authenticated user."""
        request = self.context.get("request")
        user = request.user if request else None
        if user is None:
            raise serializers.ValidationError("Authentication required.")

        institution_id = uuid.UUID(str(validated_data.pop("institution_id")))
        institution = Institution.objects.get(pk=institution_id)

        # Users may only request student memberships; admins approve/upgrade them.
        validated_data.pop("role", None)
        validated_data.pop("status", None)

        return Membership.objects.create(
            user=user,
            institution=institution,
            role=MembershipRole.STUDENT,
            status=MembershipStatus.PENDING,
        )
