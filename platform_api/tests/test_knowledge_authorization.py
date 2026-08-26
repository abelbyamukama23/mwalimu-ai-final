"""Tests for Knowledge Gateway authorization policy and scope resolution."""

import uuid

import pytest

from platform_api.apps.institutions.models import Institution
from platform_api.apps.knowledge.policies import (
    KnowledgeAuthorizationPolicy,
)
from platform_api.apps.libraries.models import (
    Library,
    LibraryAccessPolicy,
)
from platform_api.apps.memberships.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
)
from platform_api.apps.resources.models import Resource, ResourceStatus, ResourceType
from platform_api.apps.resources.object_key import generate_resource_object_key
from platform_api.apps.users.models import User


@pytest.fixture
def policy() -> KnowledgeAuthorizationPolicy:
    """Return an instance of KnowledgeAuthorizationPolicy."""
    return KnowledgeAuthorizationPolicy()


@pytest.fixture
def sample_resource(db, library_a: Library, user_a: User) -> Resource:
    """Create a sample ready resource in Library A."""
    res_id = uuid.uuid4()
    return Resource.objects.create(
        id=res_id,
        library=library_a,
        name="Biology Guide",
        resource_type=ResourceType.PDF,
        original_filename="bio.pdf",
        content_type="application/pdf",
        size=1024,
        object_key=generate_resource_object_key(library_a.pk, res_id),
        checksum="checksum-1",
        status=ResourceStatus.READY,
        created_by=user_a,
    )


@pytest.mark.django_db
def test_unauthenticated_user_has_empty_scope(
    policy: KnowledgeAuthorizationPolicy,
) -> None:
    """Anonymous or unauthenticated user resolves to an empty scope."""
    scope = policy.resolve(user=User())
    assert scope.is_empty is True
    assert len(scope.authorized_library_ids) == 0


@pytest.mark.django_db
def test_institution_admin_has_full_retrieval_scope(
    policy: KnowledgeAuthorizationPolicy,
    user_a: User,
    admin_membership_a: Membership,
    library_a: Library,
    discoverable_library_a: Library,
) -> None:
    """Institution admin has retrieval access to all active libraries."""
    scope = policy.resolve(user=user_a)
    assert scope.is_empty is False
    assert library_a.id in scope.authorized_library_ids
    assert discoverable_library_a.id in scope.authorized_library_ids


@pytest.mark.django_db
def test_discoverable_library_without_policy_denies_retrieval(
    policy: KnowledgeAuthorizationPolicy,
    user_a: User,
    membership_a: Membership,
    discoverable_library_a: Library,
) -> None:
    """RULE B: Discoverable library allows discovery, but NOT retrieval."""
    scope = policy.resolve(user=user_a)
    assert scope.is_empty is True
    assert discoverable_library_a.id not in scope.authorized_library_ids


@pytest.mark.django_db
def test_explicit_access_policy_grants_retrieval(
    policy: KnowledgeAuthorizationPolicy,
    user_a: User,
    membership_a: Membership,
    library_a: Library,
    library_student_policy_a: LibraryAccessPolicy,
) -> None:
    """Explicit LibraryAccessPolicy grants knowledge retrieval access."""
    scope = policy.resolve(user=user_a)
    assert scope.is_empty is False
    assert library_a.id in scope.authorized_library_ids


@pytest.mark.django_db
def test_scope_narrowing_with_requested_libraries(
    policy: KnowledgeAuthorizationPolicy,
    user_a: User,
    admin_membership_a: Membership,
    library_a: Library,
    discoverable_library_a: Library,
) -> None:
    """Caller can narrow its search scope to a subset of authorized libraries."""
    scope = policy.resolve(user=user_a, requested_library_ids=[library_a.id])
    assert scope.is_empty is False
    assert scope.authorized_library_ids == frozenset([library_a.id])
    assert discoverable_library_a.id not in scope.authorized_library_ids


@pytest.mark.django_db
def test_scope_widening_attempt_is_rejected(
    policy: KnowledgeAuthorizationPolicy,
    user_a: User,
    membership_a: Membership,
    library_a: Library,
    library_student_policy_a: LibraryAccessPolicy,
    library_b: Library,
) -> None:
    """Requesting an unauthorized library is dropped from the effective scope."""
    scope = policy.resolve(
        user=user_a,
        requested_library_ids=[library_a.id, library_b.id],
    )
    assert scope.is_empty is False
    assert library_a.id in scope.authorized_library_ids
    assert library_b.id not in scope.authorized_library_ids
    assert scope.authorized_library_ids == frozenset([library_a.id])


@pytest.mark.django_db
def test_disjoint_requested_libraries_yields_empty_scope(
    policy: KnowledgeAuthorizationPolicy,
    user_a: User,
    membership_a: Membership,
    library_a: Library,
    library_student_policy_a: LibraryAccessPolicy,
    library_b: Library,
) -> None:
    """Requesting only unauthorized libraries yields an empty effective scope."""
    scope = policy.resolve(user=user_a, requested_library_ids=[library_b.id])
    assert scope.is_empty is True
    assert len(scope.authorized_library_ids) == 0


@pytest.mark.django_db
def test_resource_scoping_distinguishes_none_from_empty_list(
    policy: KnowledgeAuthorizationPolicy,
    user_a: User,
    membership_a: Membership,
    library_a: Library,
    library_student_policy_a: LibraryAccessPolicy,
    sample_resource: Resource,
) -> None:
    """resource_ids=None searches all resources, while [] yields empty scope."""
    # 1. resource_ids=None -> authorized_resource_ids is None (all resources)
    scope_all = policy.resolve(user=user_a, requested_resource_ids=None)
    assert scope_all.is_empty is False
    assert scope_all.authorized_resource_ids is None

    # 2. resource_ids=[] -> authorized_resource_ids is empty frozenset (is_empty=True)
    scope_empty = policy.resolve(user=user_a, requested_resource_ids=[])
    assert scope_empty.is_empty is True
    assert scope_empty.authorized_resource_ids == frozenset()

    # 3. resource_ids=[valid_id] -> authorized_resource_ids contains valid_id
    scope_valid = policy.resolve(
        user=user_a, requested_resource_ids=[sample_resource.id]
    )
    assert scope_valid.is_empty is False
    assert scope_valid.authorized_resource_ids == frozenset([sample_resource.id])

    # 4. resource_ids=[non_existent_id] -> authorized_resource_ids is empty
    scope_invalid = policy.resolve(user=user_a, requested_resource_ids=[uuid.uuid4()])
    assert scope_invalid.is_empty is True


@pytest.mark.django_db
def test_suspended_membership_denies_retrieval(
    policy: KnowledgeAuthorizationPolicy,
    user_a: User,
    institution_a: Institution,
    library_a: Library,
) -> None:
    """Suspended institution membership yields zero authorized scope."""
    Membership.objects.create(
        user=user_a,
        institution=institution_a,
        role=MembershipRole.ADMINISTRATOR,
        status=MembershipStatus.SUSPENDED,
    )
    scope = policy.resolve(user=user_a)
    assert scope.is_empty is True


@pytest.fixture
def personal_library_a(db, user_a: User) -> Library:
    """Return a personal library owned by User A."""
    return Library.objects.create(
        owner=user_a,
        name="My Personal Notes",
        slug="my-personal-notes",
        status="active",
    )


@pytest.mark.django_db
def test_my_scope_includes_personal_library_only(
    policy: KnowledgeAuthorizationPolicy,
    user_a: User,
    admin_membership_a: Membership,
    library_a: Library,
    personal_library_a: Library,
) -> None:
    """'my' scope retrieves only the user's personal libraries."""
    my_scope = policy.resolve(user=user_a, scope_type="my")
    assert personal_library_a.id in my_scope.authorized_library_ids
    assert library_a.id not in my_scope.authorized_library_ids  # institution lib

    institution_scope = policy.resolve(user=user_a, scope_type="institution")
    assert personal_library_a.id not in institution_scope.authorized_library_ids
    assert library_a.id in institution_scope.authorized_library_ids


@pytest.mark.django_db
def test_public_scope_cannot_use_personal_document(
    policy: KnowledgeAuthorizationPolicy,
    user_a: User,
    personal_library_a: Library,
) -> None:
    """'public' scope yields no library retrieval (private doc excluded)."""
    scope = policy.resolve(user=user_a, scope_type="public")
    assert scope.is_empty is True
    assert personal_library_a.id not in scope.authorized_library_ids


@pytest.mark.django_db
def test_other_user_cannot_retrieve_private_personal_library(
    policy: KnowledgeAuthorizationPolicy,
    user_a: User,
    user_b: User,
    personal_library_a: Library,
) -> None:
    """User B cannot retrieve User A's private personal-library content."""
    scope = policy.resolve(user=user_b)
    assert scope.is_empty is True
    assert personal_library_a.id not in scope.authorized_library_ids


@pytest.mark.django_db
def test_memberless_user_with_no_library_has_empty_scope(
    policy: KnowledgeAuthorizationPolicy,
    user_a: User,
) -> None:
    """A memberless user with no libraries/memberships resolves to empty scope."""
    scope = policy.resolve(user=user_a)
    assert scope.is_empty is True
