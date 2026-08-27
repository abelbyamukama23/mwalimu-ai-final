"""Root URL configuration for the Mwalimu Platform API."""

from django.contrib import admin
from django.http import HttpRequest, JsonResponse
from django.urls import include, path
from django.views.decorators.http import require_GET
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from platform_api.apps.users.views import (
    CurrentUserView,
    LoginView,
    LogoutView,
    RefreshView,
    RegisterView,
    UserPreferenceView,
    UserProfileView,
)


@require_GET
def health_check(request: HttpRequest) -> JsonResponse:
    """Lightweight unauthenticated health check for Railway deployment."""
    return JsonResponse(
        {
            "status": "healthy",
            "service": "mwalimu-platform-api",
        },
        status=200,
    )


urlpatterns = [
    path("health/", health_check, name="health_check"),
    path("health", health_check, name="health_check_noslash"),
    path("admin/", admin.site.urls),
    path("api/v1/auth/register/", RegisterView.as_view(), name="register"),
    path("api/v1/auth/login/", LoginView.as_view(), name="token_obtain_pair"),
    path("api/v1/auth/refresh/", RefreshView.as_view(), name="token_refresh"),
    path("api/v1/auth/logout/", LogoutView.as_view(), name="auth_logout"),
    path("api/v1/auth/me/", CurrentUserView.as_view(), name="current_user"),
    path(
        "api/v1/users/profile/",
        UserProfileView.as_view(),
        name="user_profile",
    ),
    path(
        "api/v1/users/preferences/",
        UserPreferenceView.as_view(),
        name="user_preferences",
    ),
    path("api/v1/", include("platform_api.apps.institutions.urls")),
    path("api/v1/", include("platform_api.apps.memberships.urls")),
    path("api/v1/", include("platform_api.apps.libraries.urls")),
    path("api/v1/", include("platform_api.apps.resources.urls")),
    path("api/v1/", include("platform_api.apps.knowledge.urls")),
    path("api/v1/", include("platform_api.apps.agents.urls")),
    path("api/v1/", include("platform_api.apps.context.urls")),
    path("api/v1/", include("platform_api.apps.connectors.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]
