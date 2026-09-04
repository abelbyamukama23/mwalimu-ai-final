"""Tests for Academic Structure (AcademicUnit and presets)."""

import pytest
from django.db import IntegrityError
from django.urls import reverse
from rest_framework import status

from platform_api.apps.institutions.models import (
    AcademicUnit,
    AcademicUnitType,
    AuditAction,
    InstitutionalAuditEvent,
)
from platform_api.apps.memberships.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
)


@pytest.mark.django_db
def test_academic_unit_creation_and_ordering(institution_a) -> None:
    """Academic units have ordering and belong to an institution."""
    u1 = AcademicUnit.objects.create(
        institution=institution_a,
        name="Primary 1",
        code="P1",
        unit_type=AcademicUnitType.GRADE,
        order=1,
    )
    u2 = AcademicUnit.objects.create(
        institution=institution_a,
        name="Primary 2",
        code="P2",
        unit_type=AcademicUnitType.GRADE,
        order=2,
    )
    units = list(AcademicUnit.objects.filter(institution=institution_a))
    assert units == [u1, u2]


@pytest.mark.django_db
def test_academic_unit_unique_code_per_institution(institution_a) -> None:
    """Duplicate code within same active institution raises IntegrityError."""
    AcademicUnit.objects.create(
        institution=institution_a,
        name="Grade 1",
        code="G1",
        unit_type=AcademicUnitType.GRADE,
    )
    with pytest.raises(IntegrityError):
        AcademicUnit.objects.create(
            institution=institution_a,
            name="Grade 1 Duplicate",
            code="G1",
            unit_type=AcademicUnitType.GRADE,
        )


@pytest.mark.django_db
def test_academic_unit_api_crud_and_audit(
    admin_client_a, admin_membership_a, institution_a
) -> None:
    """Admin can create, update, and delete academic units with audit logging."""
    url = f"/api/v1/institutions/{institution_a.id}/academic-units/"

    # 1. Create
    resp = admin_client_a.post(
        url,
        {
            "name": "Senior 1",
            "code": "S1",
            "unit_type": AcademicUnitType.YEAR,
            "order": 1,
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED
    unit_id = resp.data["id"]

    # Verify audit event
    assert InstitutionalAuditEvent.objects.filter(
        institution=institution_a,
        action=AuditAction.ACADEMIC_UNIT_CREATED,
        target_id=unit_id,
    ).exists()

    # 2. Update
    detail_url = f"/api/v1/institutions/{institution_a.id}/academic-units/{unit_id}/"
    resp_update = admin_client_a.patch(detail_url, {"name": "Senior 1 North"}, format="json")
    assert resp_update.status_code == status.HTTP_200_OK
    assert resp_update.data["name"] == "Senior 1 North"

    # Verify audit event
    assert InstitutionalAuditEvent.objects.filter(
        institution=institution_a,
        action=AuditAction.ACADEMIC_UNIT_UPDATED,
        target_id=unit_id,
    ).exists()

    # 3. Deactivate
    resp_deact = admin_client_a.patch(detail_url, {"is_active": False}, format="json")
    assert resp_deact.status_code == status.HTTP_200_OK
    assert InstitutionalAuditEvent.objects.filter(
        institution=institution_a,
        action=AuditAction.ACADEMIC_UNIT_DEACTIVATED,
        target_id=unit_id,
    ).exists()

    # 4. Delete
    resp_del = admin_client_a.delete(detail_url)
    assert resp_del.status_code == status.HTTP_204_NO_CONTENT
    assert InstitutionalAuditEvent.objects.filter(
        institution=institution_a,
        action=AuditAction.ACADEMIC_UNIT_DELETED,
        target_id=unit_id,
    ).exists()


@pytest.mark.django_db
def test_academic_unit_apply_preset(
    admin_client_a, admin_membership_a, institution_a
) -> None:
    """Admin can apply standard structure preset (primary)."""
    url = f"/api/v1/institutions/{institution_a.id}/academic-units/apply-preset/"
    resp = admin_client_a.post(url, {"preset": "primary"}, format="json")
    assert resp.status_code == status.HTTP_200_OK
    assert len(resp.data) == 7
    codes = [u["code"] for u in resp.data]
    assert codes == ["P1", "P2", "P3", "P4", "P5", "P6", "P7"]

    # Applying again is idempotent and updates existing
    resp2 = admin_client_a.post(url, {"preset": "primary"}, format="json")
    assert resp2.status_code == status.HTTP_200_OK
    assert AcademicUnit.objects.filter(institution=institution_a).count() == 7


@pytest.mark.django_db
def test_academic_unit_member_vs_nonmember_access(
    client_b, user_b, institution_a, institution_b
) -> None:
    """Non-member cannot view academic units; active member can list."""
    url = f"/api/v1/institutions/{institution_a.id}/academic-units/"

    # user_b is not member -> 403
    resp = client_b.get(url)
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    # Add user_b as student -> 200 OK
    Membership.objects.create(
        user=user_b,
        institution=institution_a,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.ACTIVE,
    )
    resp_ok = client_b.get(url)
    assert resp_ok.status_code == status.HTTP_200_OK
