"""URL configuration for the memberships app."""

from rest_framework.routers import DefaultRouter

from .views import MembershipViewSet

router = DefaultRouter()
router.register(r"memberships", MembershipViewSet, basename="membership")

urlpatterns = router.urls
