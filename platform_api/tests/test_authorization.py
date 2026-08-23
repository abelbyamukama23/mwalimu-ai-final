"""Cross-institution authorization tests."""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from platform_api.apps.memberships.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
)


@pytest.mark.django_db
def test_user_a_cannot_see_user_b_membership(
    client_a: APIClient,
    membership_a,
    membership_b,
) -> None:
    """User A's membership list does not include User B's membership."""
    url = reverse("membership-list")
    response = client_a.get(url)

    assert response.status_code == status.HTTP_200_OK
    result_ids = {item["id"] for item in response.data["results"]}
    assert str(membership_b.pk) not in result_ids
    assert str(membership_a.pk) in result_ids


@pytest.mark.django_db
def test_user_a_cannot_retrieve_user_b_membership(
    client_a: APIClient,
    membership_b,
) -> None:
    """User A cannot retrieve User B's membership detail endpoint."""
    url = reverse("membership-detail", kwargs={"pk": str(membership_b.pk)})
    response = client_a.get(url)

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_membership_detail_only_returns_own_data(
    client_a: APIClient,
    client_b: APIClient,
    membership_a,
    membership_b,
) -> None:
    """Each user can only retrieve their own membership detail."""
    a_url = reverse("membership-detail", kwargs={"pk": str(membership_a.pk)})
    b_url = reverse("membership-detail", kwargs={"pk": str(membership_b.pk)})

    assert client_a.get(a_url).status_code == status.HTTP_200_OK
    assert client_a.get(b_url).status_code == status.HTTP_404_NOT_FOUND
    assert client_b.get(b_url).status_code == status.HTTP_200_OK
    assert client_b.get(a_url).status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_membership_creation_does_not_trust_user_id(
    client_a, user_b, institution_a
) -> None:
    """Another user's identity in a payload cannot create a membership for them."""
    url = reverse("membership-list")
    payload = {
        "institution_id": str(institution_a.pk),
        "user_id": str(user_b.pk),
        "role": MembershipRole.ADMINISTRATOR,
    }
    response = client_a.post(url, payload, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    membership = Membership.objects.get(pk=response.data["id"])
    assert membership.user.email == "user.a@example.com"
    assert membership.user_id != user_b.pk
    assert membership.role == MembershipRole.STUDENT
    assert membership.status == MembershipStatus.PENDING


@pytest.mark.django_db
def test_admin_cannot_cross_institution_boundary(
    admin_client_a: APIClient,
    user_b: APIClient,
    institution_b,
) -> None:
    """An admin of Institution A cannot access memberships in Institution B."""
    membership = Membership.objects.create(
        user=user_b,
        institution=institution_b,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.PENDING,
    )
    url = reverse("membership-detail", kwargs={"pk": str(membership.pk)})

    patch_response = admin_client_a.patch(
        url, {"status": MembershipStatus.ACTIVE}, format="json"
    )

    assert admin_client_a.get(url).status_code == status.HTTP_404_NOT_FOUND
    assert patch_response.status_code == status.HTTP_404_NOT_FOUND
    assert admin_client_a.delete(url).status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_authentication_required_for_all_slice_endpoints(
    api_client: APIClient,
    institution_a,
    membership_a,
    library_a,
) -> None:
    """All slice endpoints reject unauthenticated requests."""
    endpoints = [
        ("get", reverse("current_user")),
        ("get", reverse("institution-list")),
        ("get", reverse("institution-detail", kwargs={"pk": str(institution_a.pk)})),
        ("post", reverse("institution-list")),
        ("patch", reverse("institution-detail", kwargs={"pk": str(institution_a.pk)})),
        ("delete", reverse("institution-detail", kwargs={"pk": str(institution_a.pk)})),
        ("get", reverse("membership-list")),
        ("get", reverse("membership-detail", kwargs={"pk": str(membership_a.pk)})),
        ("post", reverse("membership-list")),
        ("patch", reverse("membership-detail", kwargs={"pk": str(membership_a.pk)})),
        ("delete", reverse("membership-detail", kwargs={"pk": str(membership_a.pk)})),
        ("get", reverse("library-list")),
        ("get", reverse("library-detail", kwargs={"pk": str(library_a.pk)})),
        ("post", reverse("library-list")),
        ("patch", reverse("library-detail", kwargs={"pk": str(library_a.pk)})),
        ("delete", reverse("library-detail", kwargs={"pk": str(library_a.pk)})),
        (
            "get",
            reverse(
                "library-accesspolicy-list", kwargs={"library_pk": str(library_a.pk)}
            ),
        ),
        (
            "post",
            reverse(
                "library-accesspolicy-list", kwargs={"library_pk": str(library_a.pk)}
            ),
        ),
    ]

    for method, url in endpoints:
        if method == "get":
            response = api_client.get(url)
        elif method == "post":
            response = api_client.post(url, {}, format="json")
        elif method == "patch":
            response = api_client.patch(url, {}, format="json")
        else:
            response = api_client.delete(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
            f"{method.upper()} {url} did not require auth"
        )
