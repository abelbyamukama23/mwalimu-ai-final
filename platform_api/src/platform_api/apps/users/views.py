from __future__ import annotations

import logging
from typing import Any, Literal, cast

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import permissions, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from platform_api.apps.users.models import EmailOTPPurpose, UserPreference, UserProfile
from platform_api.apps.users.serializers import (
    CookieTokenRefreshSerializer,
    GoogleAuthCallbackSerializer,
    GoogleAuthUrlSerializer,
    LoginAccessSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    ResendOtpSerializer,
    UserPreferenceSerializer,
    UserProfileSerializer,
    UserSerializer,
    VerifyEmailSerializer,
)
from platform_api.apps.users.services import (
    email_service,
    google_auth_service,
    otp_service,
)
from platform_api.apps.users.services.otp_service import ResendCooldownError

logger = logging.getLogger(__name__)
User = get_user_model()


def _enforce_csrf(request: Request) -> None:
    """Validate the double-submit CSRF token for cookie-authenticated endpoints.

    DRF marks view functions ``csrf_exempt`` (so a ``csrf_protect`` decorator on
    ``dispatch`` is skipped by middleware). Reuse DRF's ``SessionAuthentication``
    CSRF check, which runs on the real view path and raises 403 on failure.
    """
    SessionAuthentication().enforce_csrf(request)


def _set_refresh_cookie(response: Response, refresh: str) -> None:
    """Set the HttpOnly refresh token cookie on a response."""
    samesite_val = cast(
        Literal["Lax", "Strict", "None"] | None,
        getattr(settings, "REFRESH_COOKIE_SAMESITE", "Lax"),
    )
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        refresh,
        max_age=settings.REFRESH_COOKIE_MAX_AGE,
        path=settings.REFRESH_COOKIE_PATH,
        secure=settings.REFRESH_COOKIE_SECURE,
        httponly=settings.REFRESH_COOKIE_HTTPONLY,
        samesite=samesite_val,
    )


class CurrentUserView(GenericAPIView):  # type: ignore[type-arg]
    """Return the currently authenticated user."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get(self, request: Request) -> Response:
        """Handle GET requests for the current user."""
        UserProfile.objects.get_or_create(user=request.user)
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)


class UserProfileView(GenericAPIView):  # type: ignore[type-arg]
    """Manage the authenticated user's profile metadata."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserProfileSerializer

    def get_object(self) -> UserProfile:
        """Get or create the user's profile."""
        profile, _ = UserProfile.objects.get_or_create(user=self.request.user)
        return profile

    def get(self, request: Request) -> Response:
        """Return the user profile."""
        profile = self.get_object()
        serializer = self.get_serializer(profile)
        return Response(serializer.data)

    def patch(self, request: Request) -> Response:
        """Update the user profile."""
        profile = self.get_object()
        serializer = self.get_serializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class UserPreferenceView(GenericAPIView):  # type: ignore[type-arg]
    """Manage the authenticated user's pedagogical preferences."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserPreferenceSerializer

    def get_object(self) -> UserPreference:
        """Get or create the user's preferences."""
        preferences, _ = UserPreference.objects.get_or_create(user=self.request.user)
        return preferences

    def get(self, request: Request) -> Response:
        """Return the user preferences."""
        preferences = self.get_object()
        serializer = self.get_serializer(preferences)
        return Response(serializer.data)

    def patch(self, request: Request) -> Response:
        """Update the user preferences."""
        preferences = self.get_object()
        serializer = self.get_serializer(preferences, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class LoginView(TokenObtainPairView):
    """Log in with email/password.

    Returns the access token in JSON and delivers the refresh token via HttpOnly cookie.
    """

    serializer_class = LoginAccessSerializer

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            refresh = response.data.get("refresh")
            if refresh:
                _set_refresh_cookie(response, refresh)
                # Omit refresh token from body per cookie contract
                del response.data["refresh"]
        return response


@method_decorator(ensure_csrf_cookie, name="dispatch")
class RegisterView(GenericAPIView):  # type: ignore[type-arg]
    """Create an unverified account, generate a 6-digit OTP, and dispatch email."""

    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Generate and dispatch 6-digit verification code
        try:
            raw_otp, _ = otp_service.generate_otp(
                email=user.email,
                purpose=EmailOTPPurpose.EMAIL_VERIFICATION,
                user=user,
            )
            email_service.send_verification_otp_email(user.email, raw_otp)
        except Exception as exc:
            logger.error(
                "Failed to generate or dispatch verification OTP for %s: %s",
                user.email,
                exc,
            )

        return Response(
            {
                "email": user.email,
                "requires_verification": True,
                "message": (
                    "Account created. Please check your email for verification code."
                ),
            },
            status=status.HTTP_201_CREATED,
        )




@method_decorator(ensure_csrf_cookie, name="dispatch")
class VerifyEmailView(GenericAPIView):  # type: ignore[type-arg]
    """Verify account email using 6-digit OTP and establish authenticated session."""

    permission_classes = [permissions.AllowAny]
    serializer_class = VerifyEmailSerializer

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        otp = serializer.validated_data["otp"]
        display_name = serializer.validated_data.get("display_name", "").strip()

        user = User.objects.filter(email=email).first()
        if not user:
            return Response(
                {"error": "No account found matching this email address."},
                status=status.HTTP_404_NOT_FOUND,
            )

        success, message, _ = otp_service.verify_otp(
            email=email,
            purpose=EmailOTPPurpose.EMAIL_VERIFICATION,
            raw_otp=otp,
        )

        if not success:
            return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)

        # Mark account as verified
        user.is_email_verified = True
        user.email_verified_at = timezone.now()
        user.save(update_fields=["is_email_verified", "email_verified_at"])

        # Update display name on profile if provided
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if display_name:
            profile.display_name = display_name
            profile.save(update_fields=["display_name"])

        # Dispatch welcome email asynchronously/safely
        email_service.send_welcome_email(user.email, profile.display_name)

        # Establish authenticated session
        refresh = RefreshToken.for_user(user)
        response = Response(
            {
                "access": str(refresh.access_token),
                "user": UserSerializer(user).data,
                "message": "Email verified successfully.",
            },
            status=status.HTTP_200_OK,
        )
        _set_refresh_cookie(response, str(refresh))
        return response


class ResendOtpView(GenericAPIView):  # type: ignore[type-arg]
    """Resend a 6-digit OTP with 60s cooldown enforcement."""

    permission_classes = [permissions.AllowAny]
    serializer_class = ResendOtpSerializer

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        purpose = serializer.validated_data["purpose"]

        user = User.objects.filter(email=email).first()

        if (
            purpose == EmailOTPPurpose.EMAIL_VERIFICATION
            and user
            and user.is_email_verified
        ):
            return Response(
                {"error": "This account is already verified. You can log in directly."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            raw_otp, _ = otp_service.generate_otp(
                email=email,
                purpose=purpose,
                user=user,
            )
            if purpose == EmailOTPPurpose.EMAIL_VERIFICATION:
                email_service.send_verification_otp_email(email, raw_otp)
            elif purpose == EmailOTPPurpose.PASSWORD_RESET and user:
                email_service.send_password_reset_otp_email(email, raw_otp)
        except ResendCooldownError as exc:
            return Response(
                {"error": str(exc), "seconds_remaining": exc.seconds_remaining},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        except Exception as exc:
            logger.error("Failed to resend OTP to %s: %s", email, exc)
            return Response(
                {"error": "Failed to dispatch verification code. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {"message": "A new verification code has been sent to your email."},
            status=status.HTTP_200_OK,
        )


class PasswordResetRequestView(GenericAPIView):  # type: ignore[type-arg]
    """Request password recovery. Neutral response prevents account enumeration."""

    permission_classes = [permissions.AllowAny]
    serializer_class = PasswordResetRequestSerializer

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        user = User.objects.filter(email=email).first()

        # If user exists, generate and dispatch reset code
        if user:
            try:
                raw_otp, _ = otp_service.generate_otp(
                    email=email,
                    purpose=EmailOTPPurpose.PASSWORD_RESET,
                    user=user,
                )
                email_service.send_password_reset_otp_email(email, raw_otp)
            except ResendCooldownError:
                pass  # Neutral response even if in cooldown
            except Exception as exc:
                logger.error("Failed to send password reset code to %s: %s", email, exc)

        return Response(
            {
                "message": (
                    "If an account exists for this email, a code has been sent."
                ),
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(GenericAPIView):  # type: ignore[type-arg]
    """Validate reset OTP and set new password."""

    permission_classes = [permissions.AllowAny]
    serializer_class = PasswordResetConfirmSerializer

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        otp = serializer.validated_data["otp"]
        new_password = serializer.validated_data["new_password"]

        user = User.objects.filter(email=email).first()
        if not user:
            return Response(
                {"error": "Unable to reset password. Please request a new code."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        success, message, _ = otp_service.verify_otp(
            email=email,
            purpose=EmailOTPPurpose.PASSWORD_RESET,
            raw_otp=otp,
        )

        if not success:
            return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)

        # Set new hashed password
        user.set_password(new_password)
        user.save()

        return Response(
            {
                "message": (
                    "Your password has been successfully reset. You can now log in."
                )
            },
            status=status.HTTP_200_OK,
        )




class GoogleAuthUrlView(GenericAPIView):  # type: ignore[type-arg]
    """Return Google OAuth authorization URL and signed state token."""

    permission_classes = [permissions.AllowAny]
    serializer_class = GoogleAuthUrlSerializer

    def get(self, request: Request) -> Response:
        redirect_uri = request.query_params.get(
            "redirect_uri",
            f"{getattr(settings, 'FRONTEND_PUBLIC_URL', 'http://localhost:3000').rstrip('/')}/auth/google/callback",
        )
        auth_url, state = google_auth_service.get_google_authorization_url(redirect_uri)
        return Response({"url": auth_url, "state": state})


@method_decorator(ensure_csrf_cookie, name="dispatch")
class GoogleAuthCallbackView(GenericAPIView):  # type: ignore[type-arg]
    """Exchange authorization code and state for authenticated session."""

    permission_classes = [permissions.AllowAny]
    serializer_class = GoogleAuthCallbackSerializer

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        code = serializer.validated_data["code"]
        state = serializer.validated_data["state"]
        redirect_uri = serializer.validated_data.get("redirect_uri") or (
            f"{getattr(settings, 'FRONTEND_PUBLIC_URL', 'http://localhost:3000').rstrip('/')}/auth/google/callback"
        )

        try:
            identity = google_auth_service.exchange_google_code_and_get_identity(
                code=code,
                redirect_uri=redirect_uri,
                state=state,
            )
            user, _ = google_auth_service.resolve_or_create_google_user(identity)
        except Exception as exc:
            logger.warning("Google authentication failed: %s", exc)
            return Response(
                {"error": f"Google authentication failed: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        refresh = RefreshToken.for_user(user)
        response = Response(
            {
                "access": str(refresh.access_token),
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )
        _set_refresh_cookie(response, str(refresh))
        return response


class RefreshView(TokenRefreshView):
    """Refresh the access token using the HttpOnly cookie (with CSRF enforcement)."""

    serializer_class = CookieTokenRefreshSerializer
    authentication_classes = ()
    permission_classes = ()

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        _enforce_csrf(request)




class LogoutView(APIView):
    """Clear the refresh token cookie."""

    authentication_classes: list[type] = []
    permission_classes = [permissions.AllowAny]

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        _enforce_csrf(request)

    def post(self, request: Request) -> Response:
        response = Response(status=status.HTTP_204_NO_CONTENT)
        samesite_val = cast(
            Literal["Lax", "Strict", "None"] | None,
            getattr(settings, "REFRESH_COOKIE_SAMESITE", "Lax"),
        )
        response.delete_cookie(
            settings.REFRESH_COOKIE_NAME,
            path=settings.REFRESH_COOKIE_PATH,
            samesite=samesite_val,
        )
        return response
