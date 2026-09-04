"""Tests for Library Targeting (Universal Utility vs Academic Unit Shelf)."""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from rest_framework import status

from platform_api.apps.institutions.models import (
    AcademicUnit,
    AcademicUnitType,
    AuditAction,
    InstitutionalAuditEvent,
)
from platform_api.apps.libraries.models import (
    Library,
    LibraryScopeType,
    LibraryStatus,
    LibraryTargetType,
    LibraryVisibility,
)


@pytest.mark.django_db
def test_library_target_type_model_validation(institution_a, institution_b, user_a) -> None:
    """Model enforces academic unit targeting constraints."""
    unit_a = AcademicUnit.objects.create(
        institution=institution_a,
        name="Primary 3",
        code="P3",
        unit_type=AcademicUnitType.GRADE,
    )
    unit_b = AcademicUnit.objects.create(
        institution=institution_b,
        name="Grade 1 B",
        code="G1B",
    )

    # 1. Valid Academic Unit library
    lib_acad = Library(
        institution=institution_a,
        scope_type=LibraryScopeType.INSTITUTION,
        name="P3 Mathematics Shelf",
        slug="p3-math",
        target_type=LibraryTargetType.ACADEMIC_UNIT,
        academic_unit=unit_a,
    )
    lib_acad.full_clean()
    lib_acad.save()
    assert lib_acad.pk is not None

    # 2. Academic Unit library without unit -> ValidationError
    lib_missing_unit = Library(
        institution=institution_a,
        scope_type=LibraryScopeType.INSTITUTION,
        name="Missing Unit Shelf",
        slug="missing-unit",
        target_type=LibraryTargetType.ACADEMIC_UNIT,
        academic_unit=None,
    )
    with pytest.raises(ValidationError):
        lib_missing_unit.full_clean()

    # 3. Cross-institution unit -> ValidationError
    lib_cross = Library(
        institution=institution_a,
        scope_type=LibraryScopeType.INSTITUTION,
        name="Cross Unit Shelf",
        slug="cross-unit",
        target_type=LibraryTargetType.ACADEMIC_UNIT,
        academic_unit=unit_b,
    )
    with pytest.raises(ValidationError):
        lib_cross.full_clean()

    # 4. Personal library cannot be targeted to academic unit
    lib_personal = Library(
        owner=user_a,
        scope_type=LibraryScopeType.PERSONAL,
        name="My Shelf",
        slug="my-shelf",
        target_type=LibraryTargetType.ACADEMIC_UNIT,
        academic_unit=unit_a,
    )
    with pytest.raises(ValidationError):
        lib_personal.full_clean()


@pytest.mark.django_db
def test_library_targeting_api_crud_and_audit(
    admin_client_a, admin_membership_a, institution_a
) -> None:
    """Admin creates targeted library and updates targeting with audit logging."""
    unit = AcademicUnit.objects.create(
        institution=institution_a,
        name="Senior 4",
        code="S4",
        unit_type=AcademicUnitType.YEAR,
    )

    # 1. Create targeted library
    resp = admin_client_a.post(
        "/api/v1/libraries/",
        {
            "name": "S4 Physics Shelf",
            "slug": "s4-physics",
            "institution_id": str(institution_a.id),
            "target_type": LibraryTargetType.ACADEMIC_UNIT,
            "academic_unit_id": str(unit.id),
            "visibility": LibraryVisibility.DISCOVERABLE,
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED
    lib_id = resp.data["id"]
    assert resp.data["target_type"] == LibraryTargetType.ACADEMIC_UNIT
    assert resp.data["academic_unit"]["code"] == "S4"

    # Audit event logged
    assert InstitutionalAuditEvent.objects.filter(
        institution=institution_a,
        action=AuditAction.LIBRARY_CREATED,
        target_id=lib_id,
    ).exists()

    # 2. Update targeting to UTILITY
    resp_update = admin_client_a.patch(
        f"/api/v1/libraries/{lib_id}/",
        {"target_type": LibraryTargetType.UTILITY, "academic_unit_id": None},
        format="json",
    )
    assert resp_update.status_code == status.HTTP_200_OK
    assert resp_update.data["target_type"] == LibraryTargetType.UTILITY
    assert resp_update.data["academic_unit"] is None

    # Audit event logged for targeting update
    assert InstitutionalAuditEvent.objects.filter(
        institution=institution_a,
        action=AuditAction.LIBRARY_TARGETING_UPDATED,
        target_id=lib_id,
    ).exists()
