"""Tests for Student Academic Unit Placement."""

import pytest
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
def test_student_placement_workflow_and_audit(
    admin_client_a, admin_membership_a, institution_a, user_b
) -> None:
    """Admin places student into class and updates/clears placement with audit logging."""
    student_membership = Membership.objects.create(
        user=user_b,
        institution=institution_a,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.ACTIVE,
    )
    unit = AcademicUnit.objects.create(
        institution=institution_a,
        name="Primary 4",
        code="P4",
        unit_type=AcademicUnitType.GRADE,
        order=4,
    )

    url = f"/api/v1/memberships/{student_membership.id}/academic-placement/"

    # 1. Place student
    resp = admin_client_a.put(url, {"academic_unit_id": str(unit.id)}, format="json")
    assert resp.status_code == status.HTTP_200_OK
    student_membership.refresh_from_db()
    assert student_membership.academic_unit == unit

    # Audit event logged
    assert InstitutionalAuditEvent.objects.filter(
        institution=institution_a,
        action=AuditAction.STUDENT_PLACED,
        target_id=str(student_membership.id),
    ).exists()

    # 2. Query placement
    resp_get = admin_client_a.get(url)
    assert resp_get.status_code == status.HTTP_200_OK
    assert resp_get.data["id"] == str(unit.id)
    assert resp_get.data["code"] == "P4"

    # 3. Clear placement
    resp_clear = admin_client_a.put(url, {"academic_unit_id": None}, format="json")
    assert resp_clear.status_code == status.HTTP_200_OK
    student_membership.refresh_from_db()
    assert student_membership.academic_unit is None

    assert InstitutionalAuditEvent.objects.filter(
        institution=institution_a,
        action=AuditAction.STUDENT_UNASSIGNED,
        target_id=str(student_membership.id),
    ).exists()


@pytest.mark.django_db
def test_student_placement_cross_institution_rejection(
    admin_client_a, admin_membership_a, institution_a, institution_b, user_b
) -> None:
    """Assigning an academic unit from institution B to a member of institution A is rejected."""
    student_membership = Membership.objects.create(
        user=user_b,
        institution=institution_a,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.ACTIVE,
    )
    foreign_unit = AcademicUnit.objects.create(
        institution=institution_b,
        name="Foreign Grade 1",
        code="FG1",
        unit_type=AcademicUnitType.GRADE,
    )

    url = f"/api/v1/memberships/{student_membership.id}/academic-placement/"
    resp = admin_client_a.put(url, {"academic_unit_id": str(foreign_unit.id)}, format="json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "academic_unit_id" in resp.data


@pytest.mark.django_db
def test_student_cannot_modify_own_placement(
    client_b, user_b, institution_a
) -> None:
    """Students cannot set or modify their own academic placement."""
    student_membership = Membership.objects.create(
        user=user_b,
        institution=institution_a,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.ACTIVE,
    )
    unit = AcademicUnit.objects.create(
        institution=institution_a,
        name="Primary 5",
        code="P5",
    )
    url = f"/api/v1/memberships/{student_membership.id}/academic-placement/"
    resp = client_b.put(url, {"academic_unit_id": str(unit.id)}, format="json")
    assert resp.status_code == status.HTTP_403_FORBIDDEN
