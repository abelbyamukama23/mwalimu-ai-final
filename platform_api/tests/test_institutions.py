"""Tests for the Institution API."""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from platform_api.apps.institutions.models import Institution, InstitutionStatus
from platform_api.apps.memberships.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
)


@pytest.mark.django_db
def test_institution_creation_makes_creator_admin(client_a, user_a) -> None:
    """Creating an institution grants the creator an active administrator membership."""
    url = reverse("institution-list")
    payload = {"name": "New Institution", "slug": "new-institution"}
    response = client_a.post(url, payload, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["name"] == "New Institution"
    assert response.data["slug"] == "new-institution"
    assert response.data["status"] == InstitutionStatus.ACTIVE
    assert "id" in response.data

    institution = Institution.objects.get(slug="new-institution")
    membership = Membership.objects.get(user=user_a, institution=institution)
    assert membership.role == MembershipRole.ADMINISTRATOR
    assert membership.status == MembershipStatus.ACTIVE


@pytest.mark.django_db
def test_institution_list_is_discoverable(
    client_a, institution_a, institution_b
) -> None:
    """Any authenticated user can discover all institution metadata."""
    url = reverse("institution-list")
    response = client_a.get(url)

    assert response.status_code == status.HTTP_200_OK
    results = response.data["results"]
    assert len(results) == 2
    slugs = {item["slug"] for item in results}
    assert slugs == {"institution-a", "institution-b"}
    assert "password" not in results[0]
    assert "members" not in results[0]


@pytest.mark.django_db
def test_institution_retrieval_is_discoverable(client_a, institution_a) -> None:
    """Any authenticated user can retrieve institution metadata."""
    url = reverse("institution-detail", kwargs={"pk": str(institution_a.pk)})
    response = client_a.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["id"] == str(institution_a.pk)
    assert response.data["name"] == institution_a.name
    assert response.data["slug"] == institution_a.slug


@pytest.mark.django_db
def test_institution_slug_uniqueness(client_a) -> None:
    """Duplicate slugs are rejected."""
    Institution.objects.create(
        name="First", slug="duplicate-slug", status=InstitutionStatus.ACTIVE
    )
    url = reverse("institution-list")
    response = client_a.post(
        url, {"name": "Second", "slug": "duplicate-slug"}, format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "slug" in response.data


@pytest.mark.django_db
def test_institution_creation_requires_authentication(api_client: APIClient) -> None:
    """Unauthenticated users cannot create institutions."""
    url = reverse("institution-list")
    response = api_client.post(
        url, {"name": "Hacker U", "slug": "hacker-u"}, format="json"
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_institution_invalid_input(client_a) -> None:
    """Missing required fields return validation errors."""
    url = reverse("institution-list")
    response = client_a.post(url, {"name": ""}, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "name" in response.data


@pytest.mark.django_db
def test_institution_update_requires_admin(
    client_b, admin_client_a, institution_a
) -> None:
    """Only institution admins may update an institution."""
    url = reverse("institution-detail", kwargs={"pk": str(institution_a.pk)})

    non_admin_response = client_b.patch(
        url, {"name": "Renamed by Non-Admin"}, format="json"
    )
    assert non_admin_response.status_code == status.HTTP_403_FORBIDDEN

    admin_response = admin_client_a.patch(
        url, {"name": "Renamed by Admin"}, format="json"
    )
    assert admin_response.status_code == status.HTTP_200_OK
    institution_a.refresh_from_db()
    assert institution_a.name == "Renamed by Admin"


@pytest.mark.django_db
def test_institution_delete_requires_admin(
    client_b, admin_client_a, institution_a
) -> None:
    """Only institution admins may delete an institution."""
    url = reverse("institution-detail", kwargs={"pk": str(institution_a.pk)})

    non_admin_response = client_b.delete(url)
    assert non_admin_response.status_code == status.HTTP_403_FORBIDDEN
    assert Institution.objects.filter(pk=institution_a.pk).exists()

    admin_response = admin_client_a.delete(url)
    assert admin_response.status_code == status.HTTP_204_NO_CONTENT
    assert not Institution.objects.filter(pk=institution_a.pk).exists()


@pytest.mark.django_db
def test_admin_of_other_institution_cannot_modify_institution(
    admin_client_a, institution_b
) -> None:
    """An admin of Institution A cannot modify Institution B."""
    url = reverse("institution-detail", kwargs={"pk": str(institution_b.pk)})

    response = admin_client_a.patch(url, {"name": "Hacked by Admin A"}, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN

    response = admin_client_a.delete(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN
