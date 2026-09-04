from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AcademicUnitViewSet, InstitutionViewSet

router = DefaultRouter()
router.register(r"institutions", InstitutionViewSet, basename="institution")
router.register(r"academic-units", AcademicUnitViewSet, basename="academic-unit")

urlpatterns = [
    path(
        "institutions/<uuid:institution_pk>/academic-units/",
        AcademicUnitViewSet.as_view({"get": "list", "post": "create"}),
        name="institution-academic-units-list",
    ),
    path(
        "institutions/<uuid:institution_pk>/academic-units/apply-preset/",
        AcademicUnitViewSet.as_view({"post": "apply_preset"}),
        name="institution-academic-units-apply-preset",
    ),
    path(
        "institutions/<uuid:institution_pk>/academic-units/<uuid:pk>/",
        AcademicUnitViewSet.as_view(
            {"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"}
        ),
        name="institution-academic-units-detail",
    ),
    path(
        "institutions/<uuid:institution_pk>/academic-units/<uuid:pk>/teachers/",
        AcademicUnitViewSet.as_view({"get": "teachers"}),
        name="institution-academic-units-teachers",
    ),
    path(
        "institutions/<uuid:institution_pk>/academic-units/<uuid:pk>/students/",
        AcademicUnitViewSet.as_view({"get": "students"}),
        name="institution-academic-units-students",
    ),
    *router.urls,
]
