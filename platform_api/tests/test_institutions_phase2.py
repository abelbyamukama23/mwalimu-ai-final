"""Tests for Phase 2 Institutional Console backend capabilities."""

import uuid

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError

from platform_api.apps.institutions.models import Institution, InstitutionType
from platform_api.apps.memberships.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
)


@pytest.mark.django_db
def test_institution_creation_sets_created_by_and_type(client_a, user_a) -> None:
    """Creating an institution records created_by and saves valid institution_type."""
    url = reverse("institution-list")
    payload = {
        "name": "Acme Academy",
        "slug": "acme-academy",
        "institution_type": InstitutionType.UNIVERSITY,
    }
    response = client_a.post(url, payload, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["name"] == "Acme Academy"
    assert response.data["institution_type"] == InstitutionType.UNIVERSITY
    assert response.data["created_by_id"] == str(user_a.pk)

    inst = Institution.objects.get(slug="acme-academy")
    assert inst.created_by == user_a
    assert inst.institution_type == InstitutionType.UNIVERSITY

    # Creator is an active administrator
    membership = Membership.objects.get(user=user_a, institution=inst)
    assert membership.role == MembershipRole.ADMINISTRATOR
    assert membership.status == MembershipStatus.ACTIVE


@pytest.mark.django_db
def test_institution_creation_defaults_to_school_type(client_a, user_a) -> None:
    """When institution_type is omitted, it defaults to school."""
    url = reverse("institution-list")
    payload = {"name": "Default School", "slug": "default-school"}
    response = client_a.post(url, payload, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["institution_type"] == InstitutionType.SCHOOL

    inst = Institution.objects.get(slug="default-school")
    assert inst.institution_type == InstitutionType.SCHOOL


@pytest.mark.django_db
def test_institution_creation_rejects_invalid_type(client_a) -> None:
    """An invalid institution_type choice is rejected."""
    url = reverse("institution-list")
    payload = {
        "name": "Invalid Org",
        "slug": "invalid-org",
        "institution_type": "invalid_choice",
    }
    response = client_a.post(url, payload, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "institution_type" in response.data


@pytest.mark.django_db
def test_prevent_deleting_final_active_administrator(
    admin_client_a, admin_membership_a
) -> None:
    """An institution's sole active administrator cannot be deleted via API."""
    url = reverse("membership-detail", kwargs={"pk": str(admin_membership_a.pk)})
    response = admin_client_a.delete(url)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "final active administrator" in str(response.data)
    assert Membership.objects.filter(pk=admin_membership_a.pk).exists()


@pytest.mark.django_db
def test_prevent_model_delete_of_final_active_administrator(admin_membership_a) -> None:
    """Model.delete() enforces the orphan protection invariant."""
    with pytest.raises(DjangoValidationError):
        admin_membership_a.delete()
    assert Membership.objects.filter(pk=admin_membership_a.pk).exists()


@pytest.mark.django_db
def test_prevent_demoting_final_active_administrator(
    admin_client_a, admin_membership_a
) -> None:
    """An institution's sole active administrator cannot be demoted to student/teacher."""
    url = reverse("membership-detail", kwargs={"pk": str(admin_membership_a.pk)})
    response = admin_client_a.patch(
        url, {"role": MembershipRole.TEACHER}, format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "final active administrator" in str(response.data)

    admin_membership_a.refresh_from_db()
    assert admin_membership_a.role == MembershipRole.ADMINISTRATOR


@pytest.mark.django_db
def test_prevent_suspending_final_active_administrator(
    admin_client_a, admin_membership_a
) -> None:
    """An institution's sole active administrator cannot be suspended."""
    url = reverse("membership-detail", kwargs={"pk": str(admin_membership_a.pk)})
    response = admin_client_a.patch(
        url, {"status": MembershipStatus.SUSPENDED}, format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "final active administrator" in str(response.data)

    admin_membership_a.refresh_from_db()
    assert admin_membership_a.status == MembershipStatus.ACTIVE


@pytest.mark.django_db
def test_can_remove_admin_when_another_active_admin_exists(
    admin_client_a, admin_membership_a, user_b, institution_a
) -> None:
    """When multiple active administrators exist, one of them can be removed."""
    admin_2 = Membership.objects.create(
        user=user_b,
        institution=institution_a,
        role=MembershipRole.ADMINISTRATOR,
        status=MembershipStatus.ACTIVE,
    )

    url = reverse("membership-detail", kwargs={"pk": str(admin_2.pk)})
    response = admin_client_a.delete(url)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not Membership.objects.filter(pk=admin_2.pk).exists()
    assert Membership.objects.filter(pk=admin_membership_a.pk).exists()


@pytest.mark.django_db
def test_scoped_membership_retrieval_by_institution_id(
    admin_client_a, admin_membership_a, user_b, institution_a, institution_b
) -> None:
    """Passing ?institution_id= scopes the list strictly to that institution."""
    member_inst_a = Membership.objects.create(
        user=user_b,
        institution=institution_a,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.ACTIVE,
    )
    # Membership in institution_b
    member_inst_b = Membership.objects.create(
        user=user_b,
        institution=institution_b,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.ACTIVE,
    )

    url = f"{reverse('membership-list')}?institution_id={institution_a.pk}"
    response = admin_client_a.get(url)

    assert response.status_code == status.HTTP_200_OK
    results = response.data["results"]
    result_ids = {item["id"] for item in results}

    assert str(admin_membership_a.pk) in result_ids
    assert str(member_inst_a.pk) in result_ids
    assert str(member_inst_b.pk) not in result_ids


@pytest.mark.django_db
def test_scoped_membership_retrieval_unauthorized_institution(
    client_a, user_a, user_b, institution_b
) -> None:
    """Querying memberships of an institution where caller has no membership returns empty."""
    Membership.objects.create(
        user=user_b,
        institution=institution_b,
        role=MembershipRole.ADMINISTRATOR,
        status=MembershipStatus.ACTIVE,
    )

    url = f"{reverse('membership-list')}?institution_id={institution_b.pk}"
    response = client_a.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 0
