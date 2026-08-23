"""Tests for the Membership API."""

import pytest
from django.db import IntegrityError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from platform_api.apps.memberships.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
)


@pytest.mark.django_db
def test_membership_creation_requests_student_pending_role(
    client_a, user_a, institution_a
) -> None:
    """Self-created memberships are forced to student role and pending status."""
    url = reverse("membership-list")
    payload = {
        "institution_id": str(institution_a.pk),
        "role": MembershipRole.TEACHER,
        "status": MembershipStatus.ACTIVE,
    }
    response = client_a.post(url, payload, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["user"]["email"] == user_a.email
    assert response.data["institution"]["id"] == str(institution_a.pk)
    assert response.data["role"] == MembershipRole.STUDENT
    assert response.data["status"] == MembershipStatus.PENDING

    membership = Membership.objects.get(pk=response.data["id"])
    assert membership.user == user_a
    assert membership.institution == institution_a
    assert membership.role == MembershipRole.STUDENT
    assert membership.status == MembershipStatus.PENDING


@pytest.mark.django_db
def test_user_cannot_self_assign_administrator(client_a, user_a, institution_a) -> None:
    """A user cannot create an administrator membership for themselves."""
    url = reverse("membership-list")
    response = client_a.post(
        url,
        {
            "institution_id": str(institution_a.pk),
            "role": MembershipRole.ADMINISTRATOR,
        },
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    membership = Membership.objects.get(pk=response.data["id"])
    assert membership.user == user_a
    assert membership.role == MembershipRole.STUDENT
    assert membership.status == MembershipStatus.PENDING


@pytest.mark.django_db
def test_user_cannot_self_assign_librarian(client_a, user_a, institution_a) -> None:
    """A user cannot create a librarian membership for themselves."""
    url = reverse("membership-list")
    response = client_a.post(
        url,
        {"institution_id": str(institution_a.pk), "role": MembershipRole.LIBRARIAN},
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    membership = Membership.objects.get(pk=response.data["id"])
    assert membership.role == MembershipRole.STUDENT
    assert membership.status == MembershipStatus.PENDING


@pytest.mark.django_db
def test_user_cannot_self_assign_teacher(client_a, user_a, institution_a) -> None:
    """A user cannot create a teacher membership for themselves."""
    url = reverse("membership-list")
    response = client_a.post(
        url,
        {"institution_id": str(institution_a.pk), "role": MembershipRole.TEACHER},
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    membership = Membership.objects.get(pk=response.data["id"])
    assert membership.role == MembershipRole.STUDENT
    assert membership.status == MembershipStatus.PENDING


@pytest.mark.django_db
def test_membership_list_is_scoped_to_user(
    client_a, membership_a, membership_b
) -> None:
    """A non-admin user only sees their own memberships."""
    url = reverse("membership-list")
    response = client_a.get(url)

    assert response.status_code == status.HTTP_200_OK
    results = response.data["results"]
    assert len(results) == 1
    assert results[0]["user"]["email"] == membership_a.user.email
    assert results[0]["institution"]["id"] == str(membership_a.institution.pk)


@pytest.mark.django_db
def test_admin_can_list_all_institution_memberships(
    admin_client_a, admin_membership_a, user_b, institution_a
) -> None:
    """An institution admin sees all memberships in their institution."""
    other_membership = Membership.objects.create(
        user=user_b,
        institution=institution_a,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.PENDING,
    )

    url = reverse("membership-list")
    response = admin_client_a.get(url)

    assert response.status_code == status.HTTP_200_OK
    result_ids = {item["id"] for item in response.data["results"]}
    assert str(admin_membership_a.pk) in result_ids
    assert str(other_membership.pk) in result_ids


@pytest.mark.django_db
def test_duplicate_pending_membership_prevention(
    client_a, user_a, institution_a
) -> None:
    """A second pending/active membership request is rejected."""
    Membership.objects.create(
        user=user_a,
        institution=institution_a,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.PENDING,
    )
    url = reverse("membership-list")
    response = client_a.post(
        url, {"institution_id": str(institution_a.pk)}, format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "institution_id" in response.data or "non_field_errors" in response.data


@pytest.mark.django_db
def test_database_constraint_blocks_duplicate_active_membership(
    user_a, institution_a, membership_a
) -> None:
    """The database-level unique constraint blocks duplicate active memberships."""
    with pytest.raises(IntegrityError):
        Membership.objects.create(
            user=user_a,
            institution=institution_a,
            role=MembershipRole.STUDENT,
            status=MembershipStatus.ACTIVE,
        )


@pytest.mark.django_db
def test_inactive_membership_allows_new_active(user_a, institution_a) -> None:
    """An inactive membership does not block creating a new active one."""
    Membership.objects.create(
        user=user_a,
        institution=institution_a,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.INACTIVE,
    )
    new_membership = Membership.objects.create(
        user=user_a,
        institution=institution_a,
        role=MembershipRole.TEACHER,
        status=MembershipStatus.ACTIVE,
    )

    assert new_membership.status == MembershipStatus.ACTIVE


@pytest.mark.django_db
def test_membership_creation_requires_authentication(
    api_client: APIClient, institution_a
) -> None:
    """Unauthenticated users cannot create memberships."""
    url = reverse("membership-list")
    response = api_client.post(
        url,
        {"institution_id": str(institution_a.pk)},
        format="json",
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_membership_invalid_institution(client_a) -> None:
    """A nonexistent institution returns a validation error."""
    url = reverse("membership-list")
    response = client_a.post(
        url, {"institution_id": "00000000-0000-0000-0000-000000000000"}, format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "institution_id" in response.data


@pytest.mark.django_db
def test_admin_can_approve_and_upgrade_membership(
    admin_client_a, user_b, institution_a
) -> None:
    """An institution admin can approve a pending membership and assign a role."""
    membership = Membership.objects.create(
        user=user_b,
        institution=institution_a,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.PENDING,
    )
    url = reverse("membership-detail", kwargs={"pk": str(membership.pk)})
    response = admin_client_a.patch(
        url,
        {"role": MembershipRole.TEACHER, "status": MembershipStatus.ACTIVE},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    membership.refresh_from_db()
    assert membership.role == MembershipRole.TEACHER
    assert membership.status == MembershipStatus.ACTIVE


@pytest.mark.django_db
def test_non_admin_cannot_update_own_membership(
    client_a, user_a, institution_a
) -> None:
    """A non-admin member cannot modify their own membership role or status."""
    membership = Membership.objects.create(
        user=user_a,
        institution=institution_a,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.ACTIVE,
    )
    url = reverse("membership-detail", kwargs={"pk": str(membership.pk)})
    response = client_a.patch(
        url,
        {"role": MembershipRole.ADMINISTRATOR, "status": MembershipStatus.ACTIVE},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    membership.refresh_from_db()
    assert membership.role == MembershipRole.STUDENT


@pytest.mark.django_db
def test_non_admin_cannot_delete_own_membership(
    client_a, user_a, institution_a
) -> None:
    """A non-admin member cannot delete their own membership."""
    membership = Membership.objects.create(
        user=user_a,
        institution=institution_a,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.ACTIVE,
    )
    url = reverse("membership-detail", kwargs={"pk": str(membership.pk)})
    response = client_a.delete(url)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert Membership.objects.filter(pk=membership.pk).exists()


@pytest.mark.django_db
def test_admin_cannot_manage_other_institution_memberships(
    admin_client_a, user_b, institution_b
) -> None:
    """An admin of Institution A cannot manage memberships in Institution B."""
    membership = Membership.objects.create(
        user=user_b,
        institution=institution_b,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.PENDING,
    )
    url = reverse("membership-detail", kwargs={"pk": str(membership.pk)})

    assert (
        admin_client_a.patch(
            url, {"status": MembershipStatus.ACTIVE}, format="json"
        ).status_code
        == status.HTTP_404_NOT_FOUND
    )
    assert admin_client_a.delete(url).status_code == status.HTTP_404_NOT_FOUND
