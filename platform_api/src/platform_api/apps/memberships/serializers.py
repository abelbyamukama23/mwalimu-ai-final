"""Serializers for the memberships app."""

from typing import Any
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


class AcademicUnitMinimalSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """Minimal representation of an academic unit."""

    id = serializers.UUIDField()
    name = serializers.CharField()
    code = serializers.CharField()
    unit_type = serializers.CharField()


class MembershipSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Serializer for membership data."""

    user = MembershipUserSerializer(read_only=True)
    institution = MembershipInstitutionSerializer(read_only=True)
    institution_id = serializers.UUIDField(write_only=True)
    role = serializers.ChoiceField(choices=MembershipRole.choices, required=False)
    status = serializers.ChoiceField(choices=MembershipStatus.choices, required=False)
    academic_unit = AcademicUnitMinimalSerializer(read_only=True, allow_null=True)
    academic_unit_id = serializers.UUIDField(
        write_only=True, required=False, allow_null=True
    )

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
            "academic_unit",
            "academic_unit_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "institution",
            "academic_unit",
            "created_at",
            "updated_at",
        ]

    def validate_institution_id(self, value: uuid.UUID) -> uuid.UUID:
        """Ensure the referenced institution exists."""
        institution_id = value
        if not Institution.objects.filter(pk=institution_id).exists():
            raise serializers.ValidationError("Institution not found.")
        return institution_id

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        """Apply domain-level membership validation on creation and update."""
        if self.instance is not None:
            instance = self.instance
            new_role = attrs.get("role", instance.role)
            new_status = attrs.get("status", instance.status)

            if (
                instance.role == MembershipRole.ADMINISTRATOR
                and instance.status == MembershipStatus.ACTIVE
            ):
                if (
                    new_role != MembershipRole.ADMINISTRATOR
                    or new_status != MembershipStatus.ACTIVE
                ):
                    active_admins = (
                        Membership.objects.filter(
                            institution=instance.institution,
                            role=MembershipRole.ADMINISTRATOR,
                            status=MembershipStatus.ACTIVE,
                        )
                        .exclude(pk=instance.pk)
                        .count()
                    )
                    if active_admins == 0:
                        raise serializers.ValidationError(
                            "Cannot demote, deactivate, or suspend the final active administrator of an institution."
                        )
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


class StudentPlacementSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """Input serializer for assigning or clearing a student's academic unit placement."""

    academic_unit_id = serializers.UUIDField(allow_null=True, required=False)

    def validate_academic_unit_id(self, value: uuid.UUID | None) -> uuid.UUID | None:
        """Ensure the specified academic unit exists and belongs to the membership's institution."""
        if value is None:
            return None
        membership: Membership | None = self.context.get("membership")
        if not membership:
            raise serializers.ValidationError("Membership context is required.")
        from platform_api.apps.institutions.models import AcademicUnit

        if not AcademicUnit.objects.filter(
            pk=value, institution=membership.institution, is_active=True
        ).exists():
            raise serializers.ValidationError(
                "Active academic unit not found in this institution."
            )
        return value


class TeachingAssignmentSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Serializer for teacher-to-academic-unit teaching assignments."""

    academic_unit = AcademicUnitMinimalSerializer(read_only=True)
    academic_unit_id = serializers.UUIDField(write_only=True)
    teacher_email = serializers.EmailField(
        source="membership.user.email", read_only=True
    )
    teacher_name = serializers.SerializerMethodField()

    class Meta:
        """Serializer metadata."""

        from .models import TeachingAssignment

        model = TeachingAssignment
        fields = [
            "id",
            "institution_id",
            "membership_id",
            "teacher_email",
            "teacher_name",
            "academic_unit",
            "academic_unit_id",
            "subject",
            "status",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "institution_id",
            "membership_id",
            "teacher_email",
            "teacher_name",
            "academic_unit",
            "created_at",
            "updated_at",
        ]

    def get_teacher_name(self, obj: Any) -> str:
        """Return display name or email for the assigned teacher."""
        profile = getattr(obj.membership.user, "profile", None)
        if profile and getattr(profile, "display_name", None):
            return str(profile.display_name)
        return str(obj.membership.user.email)

    def validate_academic_unit_id(self, value: uuid.UUID) -> uuid.UUID:
        """Ensure the academic unit belongs to the same institution."""
        membership = self.context.get("membership")
        inst_id = self.context.get("institution_id") or (membership.institution_id if membership else None)
        from platform_api.apps.institutions.models import AcademicUnit

        qs = AcademicUnit.objects.filter(pk=value, is_active=True)
        if inst_id:
            qs = qs.filter(institution_id=inst_id)
        if not qs.exists():
            raise serializers.ValidationError(
                "Active academic unit not found in this institution."
            )
        return value
