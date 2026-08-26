"""Tests for the Library and LibraryAccessPolicy APIs."""

import pytest
from django.db import IntegrityError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from platform_api.apps.institutions.models import Institution, InstitutionStatus
from platform_api.apps.libraries.models import (
    Library,
    LibraryAccessPolicy,
    LibraryAccessRole,
    LibraryStatus,
    LibraryVisibility,
)
from platform_api.apps.memberships.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
)


@pytest.mark.django_db
def test_library_creation_by_institution_admin(
    admin_client_a: APIClient,
    user_a,
    institution_a,
) -> None:
    """Institution administrators may create libraries in their institution."""
    url = reverse("library-list")
    payload = {
        "institution_id": str(institution_a.pk),
        "name": "New Library",
        "slug": "new-library",
        "description": "A new library.",
        "visibility": LibraryVisibility.RESTRICTED,
    }
    response = admin_client_a.post(url, payload, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["name"] == "New Library"
    assert response.data["slug"] == "new-library"
    assert response.data["description"] == "A new library."
    assert response.data["status"] == LibraryStatus.ACTIVE
    assert response.data["visibility"] == LibraryVisibility.RESTRICTED
    assert response.data["institution"]["id"] == str(institution_a.pk)
    assert "id" in response.data

    library = Library.objects.get(slug="new-library", institution=institution_a)
    assert library.name == "New Library"


@pytest.mark.django_db
def test_library_creation_rejected_for_ordinary_member(
    client_a: APIClient,
    membership_a,
    institution_a,
) -> None:
    """Non-admin institution members cannot create libraries."""
    url = reverse("library-list")
    payload = {
        "institution_id": str(institution_a.pk),
        "name": "Hacked Library",
        "slug": "hacked-library",
    }
    response = client_a.post(url, payload, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert not Library.objects.filter(slug="hacked-library").exists()


@pytest.mark.django_db
def test_library_creation_rejected_for_non_member(
    client_a: APIClient,
    institution_b,
) -> None:
    """Users without membership in an institution cannot create its libraries."""
    url = reverse("library-list")
    payload = {
        "institution_id": str(institution_b.pk),
        "name": "Hacked Library",
        "slug": "hacked-library-b",
    }
    response = client_a.post(url, payload, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert not Library.objects.filter(slug="hacked-library-b").exists()


@pytest.mark.django_db
def test_library_retrieval_by_authorized_user(
    client_a: APIClient,
    library_student_policy_a,
    library_a,
) -> None:
    """A user with an explicit policy can retrieve the library."""
    url = reverse("library-detail", kwargs={"pk": str(library_a.pk)})
    response = client_a.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["id"] == str(library_a.pk)
    assert response.data["name"] == library_a.name
    assert response.data["institution"]["id"] == str(library_a.institution.pk)


@pytest.mark.django_db
def test_library_retrieval_by_institution_admin(
    admin_client_a: APIClient,
    library_a,
) -> None:
    """An institution admin can retrieve any library in their institution."""
    url = reverse("library-detail", kwargs={"pk": str(library_a.pk)})
    response = admin_client_a.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["id"] == str(library_a.pk)


@pytest.mark.django_db
def test_library_listing_does_not_leak_restricted_libraries(
    client_a: APIClient,
    membership_a,
    library_a,
) -> None:
    """Restricted libraries are not listed without an explicit policy."""
    url = reverse("library-list")
    response = client_a.get(url)

    assert response.status_code == status.HTTP_200_OK
    result_ids = {item["id"] for item in response.data["results"]}
    assert str(library_a.pk) not in result_ids


@pytest.mark.django_db
def test_library_listing_includes_discoverable_libraries(
    client_a: APIClient,
    membership_a,
    discoverable_library_a,
) -> None:
    """Discoverable libraries are listed for institution members."""
    url = reverse("library-list")
    response = client_a.get(url)

    assert response.status_code == status.HTTP_200_OK
    result_ids = {item["id"] for item in response.data["results"]}
    assert str(discoverable_library_a.pk) in result_ids


@pytest.mark.django_db
def test_cross_institution_library_access_denied(
    client_a: APIClient,
    membership_a,
    library_b,
) -> None:
    """A user from Institution A cannot access a library in Institution B."""
    url = reverse("library-detail", kwargs={"pk": str(library_b.pk)})

    assert client_a.get(url).status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_cross_institution_library_listing_isolated(
    client_a: APIClient,
    membership_a,
    library_b,
    discoverable_library_a,
) -> None:
    """Library listings do not include libraries from other institutions."""
    url = reverse("library-list")
    response = client_a.get(url)

    assert response.status_code == status.HTTP_200_OK
    result_ids = {item["id"] for item in response.data["results"]}
    assert str(library_b.pk) not in result_ids
    assert str(discoverable_library_a.pk) in result_ids


@pytest.mark.django_db
def test_institution_membership_does_not_imply_restricted_access(
    client_a: APIClient,
    membership_a,
    library_a,
) -> None:
    """Being an institution member does not grant access to restricted libraries."""
    url = reverse("library-detail", kwargs={"pk": str(library_a.pk)})
    response = client_a.get(url)

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_authorized_teacher_can_retrieve_library(
    client_a: APIClient,
    library_teacher_policy_a,
    library_a,
) -> None:
    """A teacher with an access policy can retrieve the library."""
    url = reverse("library-detail", kwargs={"pk": str(library_a.pk)})
    response = client_a.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["id"] == str(library_a.pk)


@pytest.mark.django_db
def test_authorized_student_can_retrieve_library(
    client_a: APIClient,
    library_student_policy_a,
    library_a,
) -> None:
    """A student with an access policy can retrieve the library."""
    url = reverse("library-detail", kwargs={"pk": str(library_a.pk)})
    response = client_a.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["id"] == str(library_a.pk)


@pytest.mark.django_db
def test_unauthorized_teacher_cannot_retrieve_restricted_library(
    client_a: APIClient,
    membership_a,
    library_a,
) -> None:
    """A teacher without an explicit policy cannot retrieve a restricted library."""
    Membership.objects.filter(pk=membership_a.pk).update(role=MembershipRole.TEACHER)
    url = reverse("library-detail", kwargs={"pk": str(library_a.pk)})
    response = client_a.get(url)

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_unauthorized_student_cannot_retrieve_restricted_library(
    client_a: APIClient,
    membership_a,
    library_a,
) -> None:
    """A student without an explicit policy cannot retrieve a restricted library."""
    Membership.objects.filter(pk=membership_a.pk).update(role=MembershipRole.STUDENT)
    url = reverse("library-detail", kwargs={"pk": str(library_a.pk)})
    response = client_a.get(url)

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_library_administrator_can_update_library(
    client_a: APIClient,
    library_admin_policy_a,
    library_a,
) -> None:
    """A library administrator can update the library."""
    url = reverse("library-detail", kwargs={"pk": str(library_a.pk)})
    response = client_a.patch(
        url,
        {"name": "Renamed by Library Admin", "description": "Updated description."},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    library_a.refresh_from_db()
    assert library_a.name == "Renamed by Library Admin"
    assert library_a.description == "Updated description."


@pytest.mark.django_db
def test_library_administrator_can_delete_library(
    client_a: APIClient,
    library_admin_policy_a,
    library_a,
) -> None:
    """A library administrator can delete the library."""
    url = reverse("library-detail", kwargs={"pk": str(library_a.pk)})
    response = client_a.delete(url)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not Library.objects.filter(pk=library_a.pk).exists()


@pytest.mark.django_db
def test_teacher_cannot_modify_library_configuration(
    client_a: APIClient,
    library_teacher_policy_a,
    library_a,
) -> None:
    """A teacher with access cannot modify library configuration."""
    url = reverse("library-detail", kwargs={"pk": str(library_a.pk)})
    response = client_a.patch(url, {"name": "Hacked by Teacher"}, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    library_a.refresh_from_db()
    assert library_a.name != "Hacked by Teacher"


@pytest.mark.django_db
def test_student_cannot_modify_library_configuration(
    client_a: APIClient,
    library_student_policy_a,
    library_a,
) -> None:
    """A student with access cannot modify library configuration."""
    url = reverse("library-detail", kwargs={"pk": str(library_a.pk)})
    response = client_a.patch(url, {"name": "Hacked by Student"}, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    library_a.refresh_from_db()
    assert library_a.name != "Hacked by Student"


@pytest.mark.django_db
def test_institution_administrator_can_update_library(
    admin_client_a: APIClient,
    library_a,
) -> None:
    """An institution administrator can update any library in their institution."""
    url = reverse("library-detail", kwargs={"pk": str(library_a.pk)})
    response = admin_client_a.patch(
        url, {"name": "Renamed by Institution Admin"}, format="json"
    )

    assert response.status_code == status.HTTP_200_OK
    library_a.refresh_from_db()
    assert library_a.name == "Renamed by Institution Admin"


@pytest.mark.django_db
def test_institution_administrator_can_delete_library(
    admin_client_a: APIClient,
    library_a,
) -> None:
    """An institution administrator can delete any library in their institution."""
    url = reverse("library-detail", kwargs={"pk": str(library_a.pk)})
    response = admin_client_a.delete(url)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not Library.objects.filter(pk=library_a.pk).exists()


@pytest.mark.django_db
def test_user_cannot_self_grant_library_administrator(
    client_a: APIClient,
    library_a,
    user_a,
) -> None:
    """A user cannot create their own library administrator access policy."""
    url = reverse("library-accesspolicy-list", kwargs={"library_pk": str(library_a.pk)})
    payload = {"user_id": str(user_a.pk), "role": LibraryAccessRole.ADMINISTRATOR}
    response = client_a.post(url, payload, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert not LibraryAccessPolicy.objects.filter(
        library=library_a, user=user_a
    ).exists()


@pytest.mark.django_db
def test_duplicate_access_policy_prevented(
    admin_client_a: APIClient,
    user_b,
    library_a,
    institution_a,
) -> None:
    """The database rejects duplicate access policies for the same user and library."""
    Membership.objects.create(
        user=user_b,
        institution=institution_a,
        role=MembershipRole.TEACHER,
        status=MembershipStatus.ACTIVE,
    )
    LibraryAccessPolicy.objects.create(
        library=library_a,
        user=user_b,
        role=LibraryAccessRole.TEACHER,
    )

    url = reverse("library-accesspolicy-list", kwargs={"library_pk": str(library_a.pk)})
    response = admin_client_a.post(
        url,
        {"user_id": str(user_b.pk), "role": LibraryAccessRole.STUDENT},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_database_constraint_blocks_duplicate_access_policy(
    user_b,
    library_a,
    institution_a,
) -> None:
    """The database-level unique constraint blocks duplicate access policies."""
    Membership.objects.create(
        user=user_b,
        institution=institution_a,
        role=MembershipRole.TEACHER,
        status=MembershipStatus.ACTIVE,
    )
    LibraryAccessPolicy.objects.create(
        library=library_a,
        user=user_b,
        role=LibraryAccessRole.TEACHER,
    )

    with pytest.raises(IntegrityError):
        LibraryAccessPolicy.objects.create(
            library=library_a,
            user=user_b,
            role=LibraryAccessRole.STUDENT,
        )


@pytest.mark.django_db
def test_cross_institution_policy_manipulation_prevented(
    admin_client_a: APIClient,
    user_b,
    library_b,
) -> None:
    """An admin of Institution A cannot manage policies for Institution B's library."""
    url = reverse("library-accesspolicy-list", kwargs={"library_pk": str(library_b.pk)})
    response = admin_client_a.post(
        url,
        {"user_id": str(user_b.pk), "role": LibraryAccessRole.ADMINISTRATOR},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_access_policy_requires_target_user_institution_membership(
    admin_client_a: APIClient,
    user_b,
    library_a,
) -> None:
    """Access policies can only be granted to members of the library's institution."""
    url = reverse("library-accesspolicy-list", kwargs={"library_pk": str(library_a.pk)})
    response = admin_client_a.post(
        url,
        {"user_id": str(user_b.pk), "role": LibraryAccessRole.STUDENT},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "user_id" in response.data
    assert not LibraryAccessPolicy.objects.filter(
        library=library_a, user=user_b
    ).exists()


@pytest.mark.django_db
def test_library_administrator_can_manage_access_policies(
    client_a: APIClient,
    library_admin_policy_a,
    user_b,
    library_a,
    institution_a,
) -> None:
    """A library administrator can create and list access policies."""
    Membership.objects.create(
        user=user_b,
        institution=institution_a,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.ACTIVE,
    )
    url = reverse("library-accesspolicy-list", kwargs={"library_pk": str(library_a.pk)})

    create_response = client_a.post(
        url,
        {"user_id": str(user_b.pk), "role": LibraryAccessRole.STUDENT},
        format="json",
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    assert create_response.data["user"]["id"] == str(user_b.pk)
    assert create_response.data["role"] == LibraryAccessRole.STUDENT

    list_response = client_a.get(url)
    assert list_response.status_code == status.HTTP_200_OK
    result_ids = {item["user"]["id"] for item in list_response.data["results"]}
    assert str(user_b.pk) in result_ids


@pytest.mark.django_db
def test_library_administrator_can_update_access_policy(
    client_a: APIClient,
    library_admin_policy_a,
    user_b,
    library_a,
    institution_a,
) -> None:
    """A library administrator can update another user's access policy role."""
    Membership.objects.create(
        user=user_b,
        institution=institution_a,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.ACTIVE,
    )
    policy = LibraryAccessPolicy.objects.create(
        library=library_a,
        user=user_b,
        role=LibraryAccessRole.STUDENT,
    )
    url = reverse(
        "library-accesspolicy-detail",
        kwargs={"library_pk": str(library_a.pk), "pk": str(policy.pk)},
    )
    response = client_a.patch(
        url,
        {"role": LibraryAccessRole.TEACHER},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    policy.refresh_from_db()
    assert policy.role == LibraryAccessRole.TEACHER


@pytest.mark.django_db
def test_library_administrator_can_delete_access_policy(
    client_a: APIClient,
    library_admin_policy_a,
    user_b,
    library_a,
    institution_a,
) -> None:
    """A library administrator can delete another user's access policy."""
    Membership.objects.create(
        user=user_b,
        institution=institution_a,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.ACTIVE,
    )
    policy = LibraryAccessPolicy.objects.create(
        library=library_a,
        user=user_b,
        role=LibraryAccessRole.STUDENT,
    )
    url = reverse(
        "library-accesspolicy-detail",
        kwargs={"library_pk": str(library_a.pk), "pk": str(policy.pk)},
    )
    response = client_a.delete(url)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not LibraryAccessPolicy.objects.filter(pk=policy.pk).exists()


@pytest.mark.django_db
def test_teacher_cannot_manage_access_policies(
    client_a: APIClient,
    library_teacher_policy_a,
    user_b,
    library_a,
) -> None:
    """A teacher cannot create or manage access policies."""
    url = reverse("library-accesspolicy-list", kwargs={"library_pk": str(library_a.pk)})
    response = client_a.post(
        url,
        {"user_id": str(user_b.pk), "role": LibraryAccessRole.STUDENT},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_archived_library_is_not_listed(
    client_a: APIClient,
    membership_a,
    institution_a,
) -> None:
    """Archived libraries are excluded from the default library list."""
    Library.objects.create(
        institution=institution_a,
        name="Archived Library",
        slug="archived-library",
        status=LibraryStatus.ARCHIVED,
        visibility=LibraryVisibility.DISCOVERABLE,
    )
    url = reverse("library-list")
    response = client_a.get(url)

    assert response.status_code == status.HTTP_200_OK
    result_names = {item["name"] for item in response.data["results"]}
    assert "Archived Library" not in result_names


@pytest.mark.django_db
def test_visibility_field_is_returned_and_editable_by_manager(
    admin_client_a: APIClient,
    library_a,
) -> None:
    """Visibility is exposed and can be changed by a library manager."""
    url = reverse("library-detail", kwargs={"pk": str(library_a.pk)})
    response = admin_client_a.patch(
        url,
        {"visibility": LibraryVisibility.DISCOVERABLE},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["visibility"] == LibraryVisibility.DISCOVERABLE
    library_a.refresh_from_db()
    assert library_a.visibility == LibraryVisibility.DISCOVERABLE


@pytest.mark.django_db
def test_library_creation_requires_authentication(
    api_client: APIClient,
    institution_a,
) -> None:
    """Unauthenticated users cannot create libraries."""
    url = reverse("library-list")
    response = api_client.post(
        url,
        {
            "institution_id": str(institution_a.pk),
            "name": "Public Library",
            "slug": "public-library",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_library_invalid_input(admin_client_a: APIClient) -> None:
    """Missing required fields return validation errors."""
    url = reverse("library-list")
    response = admin_client_a.post(url, {"name": ""}, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "name" in response.data


@pytest.mark.django_db
def test_library_slug_uniqueness_within_institution(
    admin_client_a: APIClient,
    institution_a,
    library_a,
) -> None:
    """Duplicate slugs within the same institution are rejected."""
    url = reverse("library-list")
    response = admin_client_a.post(
        url,
        {
            "institution_id": str(institution_a.pk),
            "name": "Another Library A",
            "slug": library_a.slug,
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "slug" in response.data


@pytest.mark.django_db
def test_library_slug_can_be_reused_across_institutions(
    admin_client_a: APIClient,
    admin_membership_a,
    institution_b,
) -> None:
    """The same slug may be used in different institutions."""
    Institution.objects.filter(pk=institution_b.pk).update(
        status=InstitutionStatus.ACTIVE
    )
    Membership.objects.create(
        user=admin_membership_a.user,
        institution=institution_b,
        role=MembershipRole.ADMINISTRATOR,
        status=MembershipStatus.ACTIVE,
    )
    url = reverse("library-list")
    response = admin_client_a.post(
        url,
        {
            "institution_id": str(institution_b.pk),
            "name": "Shared Slug Library",
            "slug": "library-a",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["slug"] == "library-a"


@pytest.mark.django_db
def test_client_supplied_institution_id_cannot_bypass_authorization(
    admin_client_a: APIClient,
    institution_b,
) -> None:
    """A client-supplied institution ID does not bypass cross-institution checks."""
    url = reverse("library-list")
    response = admin_client_a.post(
        url,
        {
            "institution_id": str(institution_b.pk),
            "name": "Hacked Institution B Library",
            "slug": "hacked-b",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert not Library.objects.filter(slug="hacked-b").exists()
