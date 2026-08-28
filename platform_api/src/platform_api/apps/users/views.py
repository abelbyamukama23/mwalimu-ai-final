from typing import Any, Literal, cast

from django.conf import settings
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

from .models import UserPreference, UserProfile
from .serializers import (
    CookieTokenRefreshSerializer,
    LoginAccessSerializer,
    RegisterSerializer,
    UserPreferenceSerializer,
    UserProfileSerializer,
    UserSerializer,
)


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

    Returns the access and refresh tokens in JSON, and also sets the HttpOnly
    refresh cookie.
    """

    serializer_class = LoginAccessSerializer

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            refresh = response.data.get("refresh")
            if refresh:
                _set_refresh_cookie(response, refresh)
        return response


@method_decorator(ensure_csrf_cookie, name="dispatch")
class RegisterView(GenericAPIView):  # type: ignore[type-arg]
    """Create a new account and establish an authenticated session."""

    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        response = Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )
        _set_refresh_cookie(response, str(refresh))
        return response


class RefreshView(TokenRefreshView):
    """Refresh the access token using the request body refresh token or HttpOnly cookie."""

    serializer_class = CookieTokenRefreshSerializer



class LogoutView(APIView):
    """Clear the refresh token cookie.

    Best-effort logout: there is no server-side token revocation (no blacklist),
    so clearing the cookie is the source of truth for the session.
    """

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
