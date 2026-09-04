"""Serializers for the libraries app."""

import uuid
from typing import Any

from django.contrib.auth import get_user_model
from rest_framework import serializers

from platform_api.apps.institutions.models import Institution
from platform_api.apps.memberships.models import Membership, MembershipStatus

from .models import (
    Library,
    LibraryAccessPolicy,
    LibraryAccessRole,
    LibraryScopeType,
    LibraryVisibility,
)

User = get_user_model()


class LibraryInstitutionSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Minimal institution representation nested inside library responses."""

    class Meta:
        """Serializer metadata."""

        model = Institution
        fields = ["id", "name", "slug"]


class LibrarySerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Serializer for library data."""

    institution = LibraryInstitutionSerializer(read_only=True, allow_null=True)
    institution_id = serializers.UUIDField(
        write_only=True,
        required=False,
        allow_null=True,
    )
    scope_type = serializers.CharField(read_only=True)
    is_personal = serializers.SerializerMethodField()
    visibility = serializers.ChoiceField(
        choices=LibraryVisibility.choices,
        required=False,
    )

    class Meta:
        """Serializer metadata."""

        model = Library
        fields = [
            "id",
            "scope_type",
            "is_personal",
            "institution",
            "institution_id",
            "name",
            "slug",
            "description",
            "status",
            "visibility",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "scope_type",
            "is_personal",
            "institution",
            "created_at",
            "updated_at",
        ]

    def get_is_personal(self, obj: Library) -> bool:
        """Return True if the library is a personal knowledge space."""
        return obj.scope_type == LibraryScopeType.PERSONAL

    def validate_institution_id(self, value: uuid.UUID | None) -> uuid.UUID | None:
        """Ensure the referenced institution exists if provided."""
        if value is not None and not Institution.objects.filter(pk=value).exists():
            raise serializers.ValidationError("Institution not found.")
        return value

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        """Apply scope-specific slug uniqueness validation."""
        request = self.context.get("request")
        user = getattr(request, "user", None)

        institution_id = attrs.get("institution_id")
        if self.instance is not None:
            institution_id = institution_id or self.instance.institution_id

        raw_slug = attrs.get("slug")
        if raw_slug:
            slug = str(raw_slug)
            if institution_id:
                institution_id_value = uuid.UUID(str(institution_id))
                queryset = Library.objects.filter(
                    scope_type=LibraryScopeType.INSTITUTION,
                    institution_id=institution_id_value,
                    slug=slug,
                )
                if self.instance is not None:
                    queryset = queryset.exclude(pk=self.instance.pk)
                if queryset.exists():
                    message = (
                        "A library with this slug already exists in this institution."
                    )
                    raise serializers.ValidationError({"slug": message})
            elif user and getattr(user, "is_authenticated", False):
                queryset = Library.objects.filter(
                    scope_type=LibraryScopeType.PERSONAL,
                    owner=user,
                    slug=slug,
                )
                if self.instance is not None:
                    queryset = queryset.exclude(pk=self.instance.pk)
                if queryset.exists():
                    message = "You already have a personal library with this slug."
                    raise serializers.ValidationError({"slug": message})

        return attrs


class AccessPolicyUserSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Minimal user representation nested inside access-policy responses."""

    class Meta:
        """Serializer metadata."""

        model = User
        fields = ["id", "email"]


class AccessPolicyLibrarySerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Minimal library representation nested inside access-policy responses."""

    class Meta:
        """Serializer metadata."""

        model = Library
        fields = ["id", "name", "slug"]


class LibraryAccessPolicySerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Serializer for library access policy data."""

    user = AccessPolicyUserSerializer(read_only=True)
    library = AccessPolicyLibrarySerializer(read_only=True)
    user_id = serializers.UUIDField(write_only=True)
    role = serializers.ChoiceField(
        choices=LibraryAccessRole.choices,
        required=False,
    )

    class Meta:
        """Serializer metadata."""

        model = LibraryAccessPolicy
        fields = [
            "id",
            "library",
            "user",
            "user_id",
            "role",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "library", "user", "created_at", "updated_at"]

    def validate_user_id(self, value: uuid.UUID) -> uuid.UUID:
        """Ensure the referenced user exists."""
        if not User.objects.filter(pk=value).exists():
            raise serializers.ValidationError("User not found.")
        return value

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        """Ensure the target user belongs to the library's institution."""
        library = self.context.get("library")
        if library is None:
            raise serializers.ValidationError("Library context is required.")

        raw_user_id = attrs.get("user_id")
        if raw_user_id is None and self.instance is not None:
            raw_user_id = self.instance.user_id

        if raw_user_id:
            user_id = uuid.UUID(str(raw_user_id))
            has_membership = Membership.objects.filter(
                user_id=user_id,
                institution=library.institution,
                status=MembershipStatus.ACTIVE,
            ).exists()
            if not has_membership:
                message = (
                    "The user must have an active membership "
                    "in the library's institution."
                )
                raise serializers.ValidationError({"user_id": message})

            # Prevent duplicate access policies at the application layer.
            existing_queryset = LibraryAccessPolicy.objects.filter(
                library=library,
                user_id=user_id,
            )
            if self.instance is not None:
                existing_queryset = existing_queryset.exclude(pk=self.instance.pk)
            if existing_queryset.exists():
                raise serializers.ValidationError(
                    {
                        "user_id": (
                            "This user already has an access policy for this library."
                        ),
                    },
                )

        return attrs

    def create(self, validated_data: dict[str, object]) -> LibraryAccessPolicy:
        """Create the access policy scoped to the library in the view context."""
        library = self.context.get("library")
        if library is None:
            raise serializers.ValidationError("Library context is required.")

        user_id = uuid.UUID(str(validated_data.pop("user_id")))
        user = User.objects.get(pk=user_id)
        validated_data.pop("library", None)

        role_value = str(validated_data.get("role", LibraryAccessRole.STUDENT))
        return LibraryAccessPolicy.objects.create(
            library=library,
            user=user,
            role=role_value,
        )


def mask_email(email: str) -> str:
    """Mask email for anti-enumeration in public invitation resolution."""
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = local[0] + "***"
    else:
        masked_local = local[0] + "***" + local[-1]
    return f"{masked_local}@{domain}"


class LibraryInvitationSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Full serializer for library invitations managed by librarians and administrators."""

    library_id = serializers.UUIDField(source="library.id", read_only=True)
    library_name = serializers.CharField(source="library.name", read_only=True)
    institution_id = serializers.UUIDField(
        source="institution.id", read_only=True, allow_null=True
    )
    institution_name = serializers.CharField(
        source="institution.name", read_only=True, allow_null=True
    )
    inviter_id = serializers.UUIDField(source="inviter.id", read_only=True)
    inviter_email = serializers.EmailField(source="inviter.email", read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    is_pending = serializers.BooleanField(read_only=True)

    class Meta:
        """Serializer metadata."""

        from .models import LibraryInvitation

        model = LibraryInvitation
        fields = [
            "id",
            "library_id",
            "library_name",
            "institution_id",
            "institution_name",
            "inviter_id",
            "inviter_email",
            "recipient_email",
            "recipient_user_id",
            "intended_access",
            "status",
            "token",
            "expires_at",
            "accepted_at",
            "declined_at",
            "revoked_at",
            "is_expired",
            "is_pending",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class LibraryInvitationCreateSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """Input serializer for creating a library invitation."""

    email = serializers.EmailField()
    access = serializers.ChoiceField(
        choices=LibraryAccessRole.choices,
        default=LibraryAccessRole.STUDENT,
    )


class PublicLibraryInvitationResolutionSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """Safe public serializer for resolving invitations by token without email enumeration."""

    id = serializers.UUIDField()
    library_id = serializers.UUIDField(source="library.id")
    library_name = serializers.CharField(source="library.name")
    institution_name = serializers.CharField(
        source="institution.name", allow_null=True
    )
    inviter_name = serializers.SerializerMethodField()
    recipient_email_masked = serializers.SerializerMethodField()
    intended_access = serializers.CharField()
    status = serializers.CharField()
    is_expired = serializers.BooleanField()
    is_pending = serializers.BooleanField()
    expires_at = serializers.DateTimeField()

    def get_inviter_name(self, obj: Any) -> str:
        """Return inviter display name or fallback to domain-safe representation."""
        if not obj.inviter:
            return "A librarian"
        profile = getattr(obj.inviter, "profile", None)
        if profile and profile.display_name:
            return profile.display_name
        return mask_email(obj.inviter.email)

    def get_recipient_email_masked(self, obj: Any) -> str:
        """Return masked recipient email to prevent email enumeration."""
        return mask_email(obj.recipient_email)

