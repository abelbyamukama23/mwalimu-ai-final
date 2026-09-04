from rest_framework.routers import DefaultRouter

from .views import MembershipViewSet, TeachingAssignmentViewSet

router = DefaultRouter()
router.register(r"memberships", MembershipViewSet, basename="membership")
router.register(
    r"teaching-assignments",
    TeachingAssignmentViewSet,
    basename="teaching-assignment",
)

urlpatterns = router.urls
