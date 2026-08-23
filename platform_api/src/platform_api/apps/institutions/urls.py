"""URL configuration for the institutions app."""

from rest_framework.routers import DefaultRouter

from .views import InstitutionViewSet

router = DefaultRouter()
router.register(r"institutions", InstitutionViewSet, basename="institution")

urlpatterns = router.urls
