"""Comprehensive tests for Personal Libraries alongside Institutional Libraries."""

import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from platform_api.apps.connectors.models import (
    Connector,
    ConnectorAuthType,
    ConnectorType,
)
from platform_api.apps.institutions.models import Institution
from platform_api.apps.knowledge.policies import KnowledgeAuthorizationPolicy
from platform_api.apps.libraries.models import (
    Library,
    LibraryScopeType,
    LibraryStatus,
)
from platform_api.apps.memberships.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
)
from platform_api.apps.users.models import User


@pytest.fixture
def memberless_user() -> User:
    """An independent authenticated user with no institution memberships."""
    return User.objects.create_user(
        email="independent@example.com",
        password="password123",
    )


@pytest.fixture
def other_user() -> User:
    """Another independent user."""
    return User.objects.create_user(
        email="other@example.com",
        password="password123",
    )


@pytest.fixture
def memberless_client(memberless_user: User) -> APIClient:
    """Authenticated API client for a memberless user."""
    client = APIClient()
    client.force_authenticate(user=memberless_user)
    return client


@pytest.fixture
def other_client(other_user: User) -> APIClient:
    """Authenticated API client for the second user."""
    client = APIClient()
    client.force_authenticate(user=other_user)
    return client


# ---------------------------------------------------------------------------
# 1. Personal Library Creation & Model Invariants
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_memberless_user_can_create_personal_library(
    memberless_client: APIClient,
    memberless_user: User,
) -> None:
    """A user with no institution membership can create a personal library."""
    url = reverse("library-list")
    payload = {
        "name": "My Biology Notes",
        "slug": "my-biology-notes",
        "description": "Personal research on cell biology.",
    }
    response = memberless_client.post(url, payload, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["name"] == "My Biology Notes"
    assert response.data["slug"] == "my-biology-notes"
    assert response.data["scope_type"] == LibraryScopeType.PERSONAL
    assert response.data["is_personal"] is True
    assert response.data["institution"] is None

    lib = Library.objects.get(pk=response.data["id"])
    assert lib.scope_type == LibraryScopeType.PERSONAL
    assert lib.owner == memberless_user
    assert lib.institution is None


@pytest.mark.django_db
def test_client_cannot_spoof_owner_id(
    memberless_client: APIClient,
    memberless_user: User,
    other_user: User,
) -> None:
    """Submitting another user's ID does not set that user as the owner."""
    url = reverse("library-list")
    payload = {
        "name": "Spoof Attempt",
        "slug": "spoof-attempt",
        "owner_id": str(other_user.id),
    }
    response = memberless_client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED

    lib = Library.objects.get(pk=response.data["id"])
    assert lib.owner == memberless_user  # Must always be request.user
    assert lib.owner != other_user


@pytest.mark.django_db
def test_database_ownership_constraints_enforced() -> None:
    """Database check constraint rejects invalid scope/owner/institution."""
    user = User.objects.create_user(email="dbtest@example.com", password="pw")
    institution = Institution.objects.create(name="Inst", slug="inst")

    # Personal with no owner -> raises IntegrityError
    with pytest.raises(IntegrityError), transaction.atomic():
        Library.objects.create(
            name="Invalid 1",
            slug="inv-1",
            scope_type=LibraryScopeType.PERSONAL,
            owner=None,
            institution=None,
        )

    # Personal with an institution -> raises IntegrityError
    with pytest.raises(IntegrityError), transaction.atomic():
        Library.objects.create(
            name="Invalid 2",
            slug="inv-2",
            scope_type=LibraryScopeType.PERSONAL,
            owner=user,
            institution=institution,
        )

    # Institutional with an owner -> raises IntegrityError
    with pytest.raises(IntegrityError), transaction.atomic():
        Library.objects.create(
            name="Invalid 3",
            slug="inv-3",
            scope_type=LibraryScopeType.INSTITUTION,
            owner=user,
            institution=institution,
        )

    # Institutional with no institution -> raises IntegrityError
    with pytest.raises(IntegrityError), transaction.atomic():
        Library.objects.create(
            name="Invalid 4",
            slug="inv-4",
            scope_type=LibraryScopeType.INSTITUTION,
            owner=None,
            institution=None,
        )


@pytest.mark.django_db
def test_personal_slug_uniqueness() -> None:
    """Same owner cannot create two personal libraries with the same slug."""
    user_a = User.objects.create_user(email="a@example.com", password="pw")
    user_b = User.objects.create_user(email="b@example.com", password="pw")

    # User A creates 'notes'
    Library.objects.create(
        name="Notes A",
        slug="notes",
        scope_type=LibraryScopeType.PERSONAL,
        owner=user_a,
    )

    # User B can also create 'notes' without conflict
    lib_b = Library.objects.create(
        name="Notes B",
        slug="notes",
        scope_type=LibraryScopeType.PERSONAL,
        owner=user_b,
    )
    assert lib_b.pk is not None

    # User A duplicate 'notes' raises IntegrityError
    with pytest.raises(IntegrityError), transaction.atomic():
        Library.objects.create(
            name="Duplicate Notes",
            slug="notes",
            scope_type=LibraryScopeType.PERSONAL,
            owner=user_a,
        )


# ---------------------------------------------------------------------------
# 2. Authorization & CRUD Isolation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_owner_crud_lifecycle_on_personal_library(
    memberless_client: APIClient,
    memberless_user: User,
) -> None:
    """Personal library owner can retrieve, update, and delete their library."""
    lib = Library.objects.create(
        name="My Lab Notebook",
        slug="my-lab-notebook",
        scope_type=LibraryScopeType.PERSONAL,
        owner=memberless_user,
    )

    # 1. Retrieve
    detail_url = reverse("library-detail", kwargs={"pk": str(lib.pk)})
    get_res = memberless_client.get(detail_url)
    assert get_res.status_code == status.HTTP_200_OK
    assert get_res.data["name"] == "My Lab Notebook"
    assert get_res.data["is_personal"] is True

    # 2. Update
    patch_res = memberless_client.patch(
        detail_url,
        {"name": "Updated Lab Notebook", "description": "New notes"},
        format="json",
    )
    assert patch_res.status_code == status.HTTP_200_OK
    assert patch_res.data["name"] == "Updated Lab Notebook"
    lib.refresh_from_db()
    assert lib.name == "Updated Lab Notebook"

    # 3. Delete
    del_res = memberless_client.delete(detail_url)
    assert del_res.status_code == status.HTTP_204_NO_CONTENT
    assert not Library.objects.filter(pk=lib.pk).exists()


@pytest.mark.django_db
def test_user_cannot_access_or_modify_other_users_personal_library(
    memberless_user: User,
    other_client: APIClient,
) -> None:
    """User B cannot view, edit, or delete User A's personal library."""
    lib_a = Library.objects.create(
        name="User A Private Notes",
        slug="user-a-private-notes",
        scope_type=LibraryScopeType.PERSONAL,
        owner=memberless_user,
    )

    detail_url = reverse("library-detail", kwargs={"pk": str(lib_a.pk)})

    # User B GET returns 404 (or 403)
    assert other_client.get(detail_url).status_code in (
        status.HTTP_404_NOT_FOUND,
        status.HTTP_403_FORBIDDEN,
    )

    # User B PATCH returns 404/403
    assert other_client.patch(
        detail_url, {"name": "Hacked"}, format="json"
    ).status_code in (status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN)
    lib_a.refresh_from_db()
    assert lib_a.name == "User A Private Notes"

    # User B DELETE returns 404/403
    assert other_client.delete(detail_url).status_code in (
        status.HTTP_404_NOT_FOUND,
        status.HTTP_403_FORBIDDEN,
    )
    assert Library.objects.filter(pk=lib_a.pk).exists()


@pytest.mark.django_db
def test_library_listing_returns_personal_and_authorized_institutional(
    memberless_user: User,
    memberless_client: APIClient,
    other_user: User,
) -> None:
    """Library list returns the user's personal libraries and does not leak others."""
    # User A personal library
    my_lib = Library.objects.create(
        name="User A Personal",
        slug="user-a-personal",
        scope_type=LibraryScopeType.PERSONAL,
        owner=memberless_user,
    )

    # User B personal library
    other_lib = Library.objects.create(
        name="User B Personal",
        slug="user-b-personal",
        scope_type=LibraryScopeType.PERSONAL,
        owner=other_user,
    )

    url = reverse("library-list")
    response = memberless_client.get(url)
    assert response.status_code == status.HTTP_200_OK

    result_ids = [item["id"] for item in response.data["results"]]
    assert str(my_lib.pk) in result_ids
    assert str(other_lib.pk) not in result_ids


# ---------------------------------------------------------------------------
# 3. Personal vs Institutional Connector Isolation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_personal_library_connection_isolation(
    memberless_user: User,
    memberless_client: APIClient,
    other_client: APIClient,
) -> None:
    """Connections created on personal libraries are isolated to the owner."""
    connector = Connector.objects.create(
        name="Google Drive",
        slug="google-drive",
        connector_type=ConnectorType.GOOGLE_DRIVE,
        auth_type=ConnectorAuthType.API_KEY,
    )

    personal_lib = Library.objects.create(
        name="My Biology Library",
        slug="my-biology-library",
        scope_type=LibraryScopeType.PERSONAL,
        owner=memberless_user,
    )

    # Owner creates connection
    conn_url = reverse(
        "library-connection-list-create", kwargs={"library_id": str(personal_lib.pk)}
    )
    create_res = memberless_client.post(
        conn_url,
        {
            "connector_id": str(connector.pk),
            "name": "Abel's Personal Drive",
            "configuration": {"folder_id": "folder-123"},
            "credentials": {"api_key": "secret-key-123"},
        },
        format="json",
    )
    assert create_res.status_code == status.HTTP_201_CREATED
    assert create_res.data["has_credentials"] is True

    # User B cannot list connections of User A's personal library
    assert other_client.get(conn_url).status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# 4. Knowledge Retrieval (RAG) Scope Authorization
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_knowledge_authorization_includes_personal_libraries_for_owner_only(
    memberless_user: User,
    other_user: User,
) -> None:
    """KnowledgeAuthorizationPolicy authorizes user's personal libraries for RAG."""
    lib_a = Library.objects.create(
        name="User A Research",
        slug="user-a-research",
        scope_type=LibraryScopeType.PERSONAL,
        owner=memberless_user,
        status=LibraryStatus.ACTIVE,
    )
    lib_b = Library.objects.create(
        name="User B Research",
        slug="user-b-research",
        scope_type=LibraryScopeType.PERSONAL,
        owner=other_user,
        status=LibraryStatus.ACTIVE,
    )

    policy = KnowledgeAuthorizationPolicy()

    # Scope for User A
    scope_a = policy.resolve(user=memberless_user)
    assert lib_a.pk in scope_a.authorized_library_ids
    assert lib_b.pk not in scope_a.authorized_library_ids

    # Scope for User B
    scope_b = policy.resolve(user=other_user)
    assert lib_b.pk in scope_b.authorized_library_ids
    assert lib_a.pk not in scope_b.authorized_library_ids


# ---------------------------------------------------------------------------
# 5. Institutional Library Regression Protection
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_institution_admin_can_still_create_institutional_library() -> None:
    """Institution administrators can create institutional libraries."""
    admin = User.objects.create_user(email="admin@school.ac.ke", password="pw")
    inst = Institution.objects.create(name="Alliance High", slug="alliance")
    Membership.objects.create(
        user=admin,
        institution=inst,
        role=MembershipRole.ADMINISTRATOR,
        status=MembershipStatus.ACTIVE,
    )

    client = APIClient()
    client.force_authenticate(user=admin)

    url = reverse("library-list")
    payload = {
        "institution_id": str(inst.pk),
        "name": "Form 4 Curriculum",
        "slug": "form-4-curriculum",
    }
    response = client.post(url, payload, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["scope_type"] == LibraryScopeType.INSTITUTION
    assert response.data["is_personal"] is False
    assert response.data["institution"]["id"] == str(inst.pk)

    lib = Library.objects.get(pk=response.data["id"])
    assert lib.scope_type == LibraryScopeType.INSTITUTION
    assert lib.owner is None
    assert lib.institution == inst


@pytest.mark.django_db
def test_non_admin_cannot_create_institutional_library() -> None:
    """Non-administrator institution member cannot create an institutional library."""
    student = User.objects.create_user(email="student@school.ac.ke", password="pw")
    inst = Institution.objects.create(name="Alliance High", slug="alliance")
    Membership.objects.create(
        user=student,
        institution=inst,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.ACTIVE,
    )

    client = APIClient()
    client.force_authenticate(user=student)

    url = reverse("library-list")
    payload = {
        "institution_id": str(inst.pk),
        "name": "Unauthorized Library",
        "slug": "unauthorized-library",
    }
    response = client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN
