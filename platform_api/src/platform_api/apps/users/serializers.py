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

from .models import EmailOTPPurpose, UserPreference, UserProfile

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
            "is_email_verified",
            "profile",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "email",
            "is_active",
            "is_email_verified",
            "profile",
            "created_at",
            "updated_at",
        ]


class RegisterSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """Create a new unverified user account from email and password."""

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
        """Create the user with is_email_verified=False."""
        validated_data.pop("password_confirm", None)
        return User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            is_email_verified=False,
        )


class VerifyEmailSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """Validate 6-digit OTP to verify user email address."""

    email = serializers.EmailField()
    otp = serializers.CharField(min_length=6, max_length=6)
    display_name = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True,
        default="",
        help_text="Optional display name chosen by the learner during onboarding.",
    )

    def validate_email(self, value: str) -> str:
        return value.strip().lower()

    def validate_otp(self, value: str) -> str:
        clean = value.strip()
        if not clean.isdigit() or len(clean) != 6:
            raise serializers.ValidationError(
                "Verification code must be exactly 6 digits."
            )
        return clean


class ResendOtpSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """Request a new OTP with 60-second cooldown enforcement."""

    email = serializers.EmailField()
    purpose = serializers.ChoiceField(
        choices=EmailOTPPurpose.choices,
        default=EmailOTPPurpose.EMAIL_VERIFICATION,
    )

    def validate_email(self, value: str) -> str:
        return value.strip().lower()


class PasswordResetRequestSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """Request a password reset OTP. Always responds neutrally."""

    email = serializers.EmailField()

    def validate_email(self, value: str) -> str:
        return value.strip().lower()


class PasswordResetConfirmSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """Validate reset OTP and set new account password."""

    email = serializers.EmailField()
    otp = serializers.CharField(min_length=6, max_length=6)
    new_password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
        max_length=128,
    )
    new_password_confirm = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
        max_length=128,
    )

    def validate_email(self, value: str) -> str:
        return value.strip().lower()

    def validate_otp(self, value: str) -> str:
        clean = value.strip()
        if not clean.isdigit() or len(clean) != 6:
            raise serializers.ValidationError("Reset code must be exactly 6 digits.")
        return clean

    def validate_new_password(self, value: str) -> str:
        validate_password(value)
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs.get("new_password") != attrs.get("new_password_confirm"):
            raise serializers.ValidationError(
                {"new_password_confirm": "The two password fields didn't match."},
            )
        return attrs


class GoogleAuthUrlSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """Request Google OAuth authorization URL."""

    redirect_uri = serializers.URLField(
        required=False,
        allow_blank=True,
        help_text="Frontend callback URL for OAuth redirect.",
    )


class GoogleAuthCallbackSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """Exchange authorization code and state for authenticated session."""

    code = serializers.CharField()
    state = serializers.CharField()
    redirect_uri = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )


class LoginAccessSerializer(TokenObtainPairSerializer):
    """Obtain an access/refresh pair; the caller decides how to expose refresh."""


class CookieTokenRefreshSerializer(TokenRefreshSerializer):
    """Refresh the access token using HttpOnly cookie (ignoring body token)."""


    refresh = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        request = self.context.get("request")
        cookie_refresh = (
            request.COOKIES.get(settings.REFRESH_COOKIE_NAME) if request else None
        )
        if not cookie_refresh:
            raise InvalidToken("Refresh token is missing from cookie.")

        refresh = self.token_class(cookie_refresh)
        data = {"access": str(refresh.access_token)}
        if getattr(settings, "ROTATE_REFRESH_TOKENS", False):
            refresh.set_jti()
            refresh.set_exp()
            refresh.set_iat()
            data["refresh"] = str(refresh)
        return data
