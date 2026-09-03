"""Tests for Phase 3 Institutional Console backend enhancements."""

import uuid
import pytest
from django.urls import reverse
from rest_framework import status

from platform_api.apps.libraries.models import (
    Library,
    LibraryAccessPolicy,
    LibraryAccessRole,
    LibraryScopeType,
    LibraryStatus,
    LibraryVisibility,
)
from platform_api.apps.memberships.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
)
from platform_api.apps.processing.models import ProcessingRun, ProcessingStatus
from platform_api.apps.resources.models import Resource, ResourceStatus, ResourceType


@pytest.mark.django_db
def test_scoped_library_retrieval_by_institution_id(
    admin_client_a, admin_membership_a, user_a, user_b, institution_a, institution_b
) -> None:
    """Querying libraries with ?institution_id= returns only that institution's libraries."""
    lib_inst_a = Library.objects.create(
        name="Inst A Library",
        slug="inst-a-lib",
        scope_type=LibraryScopeType.INSTITUTION,
        institution=institution_a,
        visibility=LibraryVisibility.RESTRICTED,
        status=LibraryStatus.ACTIVE,
    )
    lib_inst_b = Library.objects.create(
        name="Inst B Library",
        slug="inst-b-lib",
        scope_type=LibraryScopeType.INSTITUTION,
        institution=institution_b,
        visibility=LibraryVisibility.DISCOVERABLE,
        status=LibraryStatus.ACTIVE,
    )
    lib_personal = Library.objects.create(
        name="Personal Library A",
        slug="personal-lib-a",
        scope_type=LibraryScopeType.PERSONAL,
        owner=user_a,
        status=LibraryStatus.ACTIVE,
    )

    url = f"{reverse('library-list')}?institution_id={institution_a.pk}"
    response = admin_client_a.get(url)

    assert response.status_code == status.HTTP_200_OK
    results = response.data["results"]
    result_ids = {item["id"] for item in results}

    assert str(lib_inst_a.pk) in result_ids
    assert str(lib_inst_b.pk) not in result_ids
    assert str(lib_personal.pk) not in result_ids


@pytest.mark.django_db
def test_scoped_library_retrieval_unauthorized_institution(
    client_a, user_a, institution_b
) -> None:
    """Querying libraries for an institution where caller is not a member returns empty."""
    Library.objects.create(
        name="Inst B Secret",
        slug="inst-b-secret",
        scope_type=LibraryScopeType.INSTITUTION,
        institution=institution_b,
        visibility=LibraryVisibility.RESTRICTED,
        status=LibraryStatus.ACTIVE,
    )

    url = f"{reverse('library-list')}?institution_id={institution_b.pk}"
    response = client_a.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 0


@pytest.mark.django_db
def test_processing_status_returns_error_details(
    admin_client_a, admin_membership_a, library_a, user_a
) -> None:
    """Processing status endpoint includes error_code and error_message when present."""
    resource = Resource.objects.create(
        library=library_a,
        name="Failed Textbook",
        resource_type=ResourceType.PDF,
        original_filename="textbook.pdf",
        content_type="application/pdf",
        size=1024,
        object_key="failed_key",
        checksum="failed_checksum",
        status=ResourceStatus.READY,
        created_by=user_a,
    )

    run = ProcessingRun.objects.create(
        resource=resource,
        library=library_a,
        status=ProcessingStatus.FAILED,
        current_stage="extract",
        is_active=True,
        extractor_version="1",
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
        error_code="CORRUPT_PDF",
        error_message="PDF contains unreadable font tables.",
    )

    url = reverse(
        "resource-processing-status",
        kwargs={"library_pk": str(library_a.pk), "pk": str(resource.pk)},
    )
    response = admin_client_a.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == ProcessingStatus.FAILED
    assert response.data["error_code"] == "CORRUPT_PDF"
    assert response.data["error_message"] == "PDF contains unreadable font tables."
