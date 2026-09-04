"""Tests for Teacher Academic Unit Assignments."""

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
    TeachingAssignment,
    TeachingAssignmentStatus,
)


@pytest.mark.django_db
def test_teacher_assignment_crud_and_audit(
    admin_client_a, admin_membership_a, institution_a, user_b
) -> None:
    """Admin assigns teacher to academic unit with subject and removes assignment."""
    teacher_membership = Membership.objects.create(
        user=user_b,
        institution=institution_a,
        role=MembershipRole.TEACHER,
        status=MembershipStatus.ACTIVE,
    )
    unit = AcademicUnit.objects.create(
        institution=institution_a,
        name="Senior 2",
        code="S2",
        unit_type=AcademicUnitType.YEAR,
        order=2,
    )

    url = f"/api/v1/memberships/{teacher_membership.id}/teaching-assignments/"

    # 1. Create assignment
    resp = admin_client_a.post(
        url,
        {"academic_unit_id": str(unit.id), "subject": "Mathematics"},
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED
    assignment_id = resp.data["id"]
    assert resp.data["subject"] == "Mathematics"

    # Audit event logged
    assert InstitutionalAuditEvent.objects.filter(
        institution=institution_a,
        action=AuditAction.TEACHER_ASSIGNED,
        target_id=assignment_id,
    ).exists()

    # 2. List assignments for this teacher
    resp_list = admin_client_a.get(url)
    assert resp_list.status_code == status.HTTP_200_OK
    assert len(resp_list.data) == 1

    # 3. List teachers for the academic unit
    unit_teachers_url = f"/api/v1/institutions/{institution_a.id}/academic-units/{unit.id}/teachers/"
    resp_unit_teachers = admin_client_a.get(unit_teachers_url)
    assert resp_unit_teachers.status_code == status.HTTP_200_OK
    assert len(resp_unit_teachers.data) == 1
    assert resp_unit_teachers.data[0]["teacher_email"] == user_b.email

    # 4. Delete assignment
    delete_url = f"/api/v1/teaching-assignments/{assignment_id}/"
    resp_del = admin_client_a.delete(delete_url)
    assert resp_del.status_code == status.HTTP_204_NO_CONTENT

    assert not TeachingAssignment.objects.filter(pk=assignment_id).exists()
    assert InstitutionalAuditEvent.objects.filter(
        institution=institution_a,
        action=AuditAction.TEACHER_UNASSIGNED,
        target_id=assignment_id,
    ).exists()


@pytest.mark.django_db
def test_teacher_assignment_non_teacher_rejected(
    admin_client_a, admin_membership_a, institution_a, user_b
) -> None:
    """Cannot create teaching assignment for student role."""
    student_membership = Membership.objects.create(
        user=user_b,
        institution=institution_a,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.ACTIVE,
    )
    unit = AcademicUnit.objects.create(
        institution=institution_a,
        name="Grade 3",
        code="G3",
    )
    url = f"/api/v1/memberships/{student_membership.id}/teaching-assignments/"
    resp = admin_client_a.post(
        url,
        {"academic_unit_id": str(unit.id), "subject": "Art"},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_teacher_assignment_cross_institution_rejected(
    admin_client_a, admin_membership_a, institution_a, institution_b, user_b
) -> None:
    """Cannot assign teacher in Inst A to unit in Inst B."""
    teacher_membership = Membership.objects.create(
        user=user_b,
        institution=institution_a,
        role=MembershipRole.TEACHER,
        status=MembershipStatus.ACTIVE,
    )
    foreign_unit = AcademicUnit.objects.create(
        institution=institution_b,
        name="Foreign Form 1",
        code="FF1",
    )
    url = f"/api/v1/memberships/{teacher_membership.id}/teaching-assignments/"
    resp = admin_client_a.post(
        url,
        {"academic_unit_id": str(foreign_unit.id), "subject": "Science"},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
