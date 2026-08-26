from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenRefreshSerializer,
)

from .models import UserPreference, UserProfile

User = get_user_model()


class UserProfileSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Serializer for user profile metadata."""

    class Meta:
        """Serializer metadata."""

        model = UserProfile
        fields = [
            "id",
            "display_name",
            "avatar_url",
            "phone_number",
            "bio",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class UserPreferenceSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Serializer for user pedagogical and reasoning preferences."""

    class Meta:
        """Serializer metadata."""

        model = UserPreference
        fields = [
            "id",
            "pedagogical_style",
            "explanation_depth",
            "response_language",
            "cross_session_memory",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class UserSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Serializer for reading user data."""

    profile = UserProfileSerializer(read_only=True)

    class Meta:
        """Serializer metadata."""

        model = User
        fields = [
            "id",
            "email",
            "is_active",
            "profile",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "email",
            "is_active",
            "profile",
            "created_at",
            "updated_at",
        ]


class RegisterSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """Create a new user account from email, password, and password confirmation.

    ``email`` is normalized (trimmed/lowercased) and checked for uniqueness. The
    password is validated against ``AUTH_PASSWORD_VALIDATORS`` and must match
    ``password_confirm`` so a typo can never silently create an account.
    """

    email = serializers.EmailField()
    password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
        max_length=128,
    )
    password_confirm = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
        max_length=128,
    )

    def validate_email(self, value: str) -> str:
        """Normalize the email and reject duplicates."""
        value = value.strip().lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "An account with this email already exists. Log in instead.",
            )
        return value

    def validate_password(self, value: str) -> str:
        """Run the configured password validators against the new password."""
        validate_password(value)
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Ensure the password confirmation matches the password."""
        if attrs.get("password") != attrs.get("password_confirm"):
            raise serializers.ValidationError(
                {"password_confirm": "The two password fields didn't match."},
            )
        return attrs

    def create(self, validated_data: dict[str, Any]) -> Any:
        """Create the user with a hashed password."""
        validated_data.pop("password_confirm", None)
        return User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
        )


class LoginAccessSerializer(TokenObtainPairSerializer):
    """Obtain an access/refresh pair; the caller decides how to expose refresh."""


class CookieTokenRefreshSerializer(TokenRefreshSerializer):
    """Refresh the access token using the HttpOnly refresh cookie, not the body.

    The `refresh` token comes from the request cookie (named by
    ``settings.REFRESH_COOKIE_NAME``). It is never accepted from the request body
    and is never returned to the client.
    """

    refresh = serializers.CharField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        request = self.context.get("request")
        refresh_token = (
            request.COOKIES.get(settings.REFRESH_COOKIE_NAME) if request else None
        )
        if not refresh_token:
            raise InvalidToken("Refresh token cookie missing.")
        # The body field is not required; nothing is read from the request body.
        attrs.pop("refresh", None)
        refresh = self.token_class(refresh_token)
        data = {"access": str(refresh.access_token)}
        if getattr(settings, "ROTATE_REFRESH_TOKENS", False):
            refresh.set_jti()
            refresh.set_exp()
            refresh.set_iat()
            data["refresh"] = str(refresh)
        return data
