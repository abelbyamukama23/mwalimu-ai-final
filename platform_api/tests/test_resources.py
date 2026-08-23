"""Tests for the Resource API and object-storage boundary."""

import uuid
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from platform_api.apps.resources.checksum import sha256_checksum
from platform_api.apps.resources.fake_storage import FakeStorage
from platform_api.apps.resources.models import Resource, ResourceStatus, ResourceType
from platform_api.apps.resources.object_key import generate_resource_object_key
from platform_api.apps.resources.storage import get_object_storage
from platform_api.apps.resources.validators import ResourceValidationError


def _upload_payload(
    name: str,
    resource_type: str,
    filename: str,
    content: bytes,
    content_type: str = "",
) -> dict:
    """Return a multipart payload for resource creation."""
    return {
        "name": name,
        "resource_type": resource_type,
        "file": SimpleUploadedFile(filename, content, content_type=content_type),
    }


def _content_disposition_filename(response) -> str:
    """Return the filename from a Content-Disposition header."""
    header = response.get("Content-Disposition", "")
    if "filename=" in header:
        return header.split("filename=")[-1].strip('"')
    return ""


@pytest.mark.django_db
def test_resource_creation_by_library_administrator(
    client_a: APIClient,
    library_admin_policy_a,
    library_a,
) -> None:
    """A library administrator can upload a resource."""
    url = reverse("resource-list", kwargs={"library_pk": str(library_a.pk)})
    content = b"%PDF-1.4 test pdf content"
    response = client_a.post(
        url,
        _upload_payload(
            "My PDF", ResourceType.PDF, "doc.pdf", content, "application/pdf"
        ),
        format="multipart",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["name"] == "My PDF"
    assert response.data["resource_type"] == ResourceType.PDF
    assert response.data["status"] == ResourceStatus.READY
    assert response.data["size"] == len(content)
    assert response.data["checksum"] == sha256_checksum(BytesIO(content))
    assert response.data["original_filename"] == "doc.pdf"
    assert response.data["library"]["id"] == str(library_a.pk)

    resource = Resource.objects.get(pk=response.data["id"])
    expected_key = generate_resource_object_key(library_a.pk, resource.pk)
    assert resource.object_key == expected_key
    assert FakeStorage().exists(resource.object_key)


@pytest.mark.django_db
def test_resource_creation_by_institution_administrator(
    admin_client_a: APIClient,
    library_a,
) -> None:
    """An institution administrator can upload a resource to any library."""
    url = reverse("resource-list", kwargs={"library_pk": str(library_a.pk)})
    content = b"Plain text resource content."
    response = admin_client_a.post(
        url,
        _upload_payload(
            "My Text", ResourceType.TXT, "notes.txt", content, "text/plain"
        ),
        format="multipart",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["status"] == ResourceStatus.READY
    resource = Resource.objects.get(pk=response.data["id"])
    assert FakeStorage().exists(resource.object_key)


@pytest.mark.django_db
def test_unauthorized_resource_creation_rejected(
    client_a: APIClient,
    membership_a,
    library_a,
) -> None:
    """A user without library management access cannot upload resources."""
    url = reverse("resource-list", kwargs={"library_pk": str(library_a.pk)})
    response = client_a.post(
        url,
        _upload_payload("Hack", ResourceType.TXT, "hack.txt", b"hack", "text/plain"),
        format="multipart",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert Resource.objects.count() == 0


@pytest.mark.django_db
def test_resource_listing_by_authorized_user(
    client_a: APIClient,
    library_student_policy_a,
    library_a,
) -> None:
    """A user with library access can list resources."""
    resource = Resource.objects.create(
        library=library_a,
        name="Listed Resource",
        resource_type=ResourceType.PDF,
        original_filename="listed.pdf",
        content_type="application/pdf",
        size=12,
        object_key=generate_resource_object_key(library_a.pk, uuid.uuid4()),
        checksum="abc",
        status=ResourceStatus.READY,
        created_by=library_student_policy_a.user,
    )
    url = reverse("resource-list", kwargs={"library_pk": str(library_a.pk)})
    response = client_a.get(url)

    assert response.status_code == status.HTTP_200_OK
    result_ids = {item["id"] for item in response.data["results"]}
    assert str(resource.pk) in result_ids


@pytest.mark.django_db
def test_resource_retrieval_by_authorized_user(
    client_a: APIClient,
    library_teacher_policy_a,
    library_a,
    user_a,
) -> None:
    """A user with library access can retrieve resource metadata."""
    resource = Resource.objects.create(
        library=library_a,
        name="Retrieved Resource",
        resource_type=ResourceType.PDF,
        original_filename="retrieved.pdf",
        content_type="application/pdf",
        size=12,
        object_key=generate_resource_object_key(library_a.pk, uuid.uuid4()),
        checksum="abc",
        status=ResourceStatus.READY,
        created_by=user_a,
    )
    url = reverse(
        "resource-detail",
        kwargs={"library_pk": str(library_a.pk), "pk": str(resource.pk)},
    )
    response = client_a.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["id"] == str(resource.pk)
    assert response.data["name"] == resource.name


@pytest.mark.django_db
def test_cross_institution_resource_isolation(
    client_a: APIClient,
    membership_a,
    library_b,
    user_b,
) -> None:
    """A user from Institution A cannot see resources in Institution B."""
    resource = Resource.objects.create(
        library=library_b,
        name="Other Resource",
        resource_type=ResourceType.PDF,
        original_filename="other.pdf",
        content_type="application/pdf",
        size=12,
        object_key=generate_resource_object_key(library_b.pk, uuid.uuid4()),
        checksum="abc",
        status=ResourceStatus.READY,
        created_by=user_b,
    )
    url = reverse(
        "resource-detail",
        kwargs={"library_pk": str(library_b.pk), "pk": str(resource.pk)},
    )
    response = client_a.get(url)

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_restricted_library_resource_authorization(
    client_a: APIClient,
    membership_a,
    library_a,
) -> None:
    """A plain institution member cannot list resources in a restricted library."""
    url = reverse("resource-list", kwargs={"library_pk": str(library_a.pk)})
    response = client_a.get(url)

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_resource_metadata_validation(
    client_a: APIClient,
    library_admin_policy_a,
    library_a,
) -> None:
    """Missing required metadata returns validation errors."""
    url = reverse("resource-list", kwargs={"library_pk": str(library_a.pk)})
    response = client_a.post(
        url,
        {"resource_type": ResourceType.PDF},
        format="multipart",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "name" in response.data


@pytest.mark.django_db
def test_unsupported_file_type_rejected(
    client_a: APIClient,
    library_admin_policy_a,
    library_a,
) -> None:
    """Unsupported resource types are rejected."""
    url = reverse("resource-list", kwargs={"library_pk": str(library_a.pk)})
    response = client_a.post(
        url,
        {
            "name": "Bad",
            "resource_type": "exe",
            "file": BytesIO(b"binary"),
        },
        format="multipart",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "resource_type" in response.data


@pytest.mark.django_db
def test_file_size_validation(
    client_a: APIClient,
    library_admin_policy_a,
    library_a,
    settings,
) -> None:
    """Files exceeding the configured maximum size are rejected."""
    settings.RESOURCE_MAX_UPLOAD_SIZE = 10
    url = reverse("resource-list", kwargs={"library_pk": str(library_a.pk)})
    response = client_a.post(
        url,
        _upload_payload("Big", ResourceType.TXT, "big.txt", b"x" * 11, "text/plain"),
        format="multipart",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "file" in response.data


@pytest.mark.django_db
def test_safe_object_key_generation(
    library_a,
) -> None:
    """Generated object keys are deterministic and scoped to the library."""
    resource_id = uuid.uuid4()
    key = generate_resource_object_key(library_a.pk, resource_id)

    assert key == f"libraries/{library_a.pk}/resources/{resource_id}/original"
    assert ".." not in key
    assert key.startswith(f"libraries/{library_a.pk}/")


@pytest.mark.django_db
def test_path_traversal_filename_rejected(
    client_a: APIClient,
    library_admin_policy_a,
    library_a,
) -> None:
    """Filenames containing path traversal are rejected."""
    from platform_api.apps.resources.validators import validate_resource_upload

    with pytest.raises(ResourceValidationError):
        validate_resource_upload(
            ResourceType.TXT,
            "../../../etc/passwd.txt",
            "text/plain",
            4,
            BytesIO(b"text"),
        )


@pytest.mark.django_db
def test_original_filename_handling(
    client_a: APIClient,
    library_admin_policy_a,
    library_a,
) -> None:
    """The original filename is stored but not used as the storage key."""
    url = reverse("resource-list", kwargs={"library_pk": str(library_a.pk)})
    response = client_a.post(
        url,
        _upload_payload(
            "Named", ResourceType.TXT, "my notes.txt", b"content", "text/plain"
        ),
        format="multipart",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["original_filename"] == "my notes.txt"
    resource = Resource.objects.get(pk=response.data["id"])
    assert resource.object_key != "my notes.txt"


@pytest.mark.django_db
def test_sha256_checksum_generation(
    client_a: APIClient,
    library_admin_policy_a,
    library_a,
) -> None:
    """The stored checksum is the SHA-256 digest of the uploaded content."""
    url = reverse("resource-list", kwargs={"library_pk": str(library_a.pk)})
    content = b"checksum test content"
    response = client_a.post(
        url,
        _upload_payload(
            "Checksum", ResourceType.TXT, "checksum.txt", content, "text/plain"
        ),
        format="multipart",
    )

    assert response.status_code == status.HTTP_201_CREATED
    expected = sha256_checksum(BytesIO(content))
    assert response.data["checksum"] == expected
    resource = Resource.objects.get(pk=response.data["id"])
    assert resource.checksum == expected


@pytest.mark.django_db
def test_object_upload(
    library_admin_policy_a,
    library_a,
) -> None:
    """Uploaded content is stored in the configured object-storage backend."""
    from platform_api.apps.resources.storage import get_object_storage

    storage = get_object_storage()
    key = generate_resource_object_key(library_a.pk, uuid.uuid4())
    content = b"stored object content"
    storage.upload(key, BytesIO(content), "text/plain", len(content))

    assert storage.exists(key)
    downloaded = storage.download(key).read()
    assert downloaded == content


@pytest.mark.django_db
def test_object_exists(
    library_a,
) -> None:
    """The storage backend correctly reports object existence."""
    storage = get_object_storage()
    key = generate_resource_object_key(library_a.pk, uuid.uuid4())

    assert not storage.exists(key)
    storage.upload(key, BytesIO(b"x"), "text/plain", 1)
    assert storage.exists(key)
    storage.delete(key)
    assert not storage.exists(key)


@pytest.mark.django_db
def test_object_deletion(
    client_a: APIClient,
    library_admin_policy_a,
    library_a,
) -> None:
    """Deleting a resource removes both the database record and stored object."""
    url = reverse("resource-list", kwargs={"library_pk": str(library_a.pk)})
    response = client_a.post(
        url,
        _upload_payload(
            "To Delete", ResourceType.TXT, "delete.txt", b"delete me", "text/plain"
        ),
        format="multipart",
    )
    resource = Resource.objects.get(pk=response.data["id"])
    detail_url = reverse(
        "resource-detail",
        kwargs={"library_pk": str(library_a.pk), "pk": str(resource.pk)},
    )

    delete_response = client_a.delete(detail_url)
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT
    assert not Resource.objects.filter(pk=resource.pk).exists()
    assert not FakeStorage().exists(resource.object_key)


@pytest.mark.django_db
def test_download_returns_original_content(
    client_a: APIClient,
    library_admin_policy_a,
    library_a,
) -> None:
    """The download endpoint returns the original binary."""
    url = reverse("resource-list", kwargs={"library_pk": str(library_a.pk)})
    content = b"downloadable content"
    response = client_a.post(
        url,
        _upload_payload(
            "Download", ResourceType.TXT, "download.txt", content, "text/plain"
        ),
        format="multipart",
    )
    resource = Resource.objects.get(pk=response.data["id"])
    download_url = reverse(
        "resource-download",
        kwargs={"library_pk": str(library_a.pk), "pk": str(resource.pk)},
    )

    download_response = client_a.get(download_url)
    assert download_response.status_code == status.HTTP_200_OK
    assert b"".join(download_response.streaming_content) == content
    assert _content_disposition_filename(download_response) == "download.txt"


@pytest.mark.django_db
def test_deletion_failure_behavior(
    client_a: APIClient,
    library_admin_policy_a,
    library_a,
    monkeypatch,
) -> None:
    """If storage deletion fails, the database record is preserved."""
    url = reverse("resource-list", kwargs={"library_pk": str(library_a.pk)})
    response = client_a.post(
        url,
        _upload_payload(
            "Fail Delete", ResourceType.TXT, "fail.txt", b"content", "text/plain"
        ),
        format="multipart",
    )
    resource = Resource.objects.get(pk=response.data["id"])
    detail_url = reverse(
        "resource-detail",
        kwargs={"library_pk": str(library_a.pk), "pk": str(resource.pk)},
    )

    def _raise(*args, **kwargs):
        raise RuntimeError("storage down")

    monkeypatch.setattr(FakeStorage, "delete", _raise)
    delete_response = client_a.delete(detail_url)

    assert delete_response.status_code == status.HTTP_400_BAD_REQUEST
    assert Resource.objects.filter(pk=resource.pk).exists()


@pytest.mark.django_db
def test_archived_resource_not_listed(
    client_a: APIClient,
    library_student_policy_a,
    library_a,
    user_a,
) -> None:
    """Archived resources are excluded from the default resource list."""
    Resource.objects.create(
        library=library_a,
        name="Archived Resource",
        resource_type=ResourceType.PDF,
        original_filename="archived.pdf",
        content_type="application/pdf",
        size=12,
        object_key=generate_resource_object_key(library_a.pk, uuid.uuid4()),
        checksum="abc",
        status=ResourceStatus.ARCHIVED,
        created_by=user_a,
    )
    url = reverse("resource-list", kwargs={"library_pk": str(library_a.pk)})
    response = client_a.get(url)

    assert response.status_code == status.HTTP_200_OK
    result_names = {item["name"] for item in response.data["results"]}
    assert "Archived Resource" not in result_names


@pytest.mark.django_db
def test_authentication_required_for_resource_endpoints(
    api_client: APIClient,
    library_a,
) -> None:
    """Resource endpoints reject unauthenticated requests."""
    endpoints = [
        ("get", reverse("resource-list", kwargs={"library_pk": str(library_a.pk)})),
        ("post", reverse("resource-list", kwargs={"library_pk": str(library_a.pk)})),
    ]
    for method, url in endpoints:
        if method == "get":
            response = api_client.get(url)
        else:
            response = api_client.post(url, {}, format="multipart")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
            f"{method.upper()} {url} did not require auth"
        )


@pytest.mark.django_db
def test_pdf_mime_validation(
    client_a: APIClient,
    library_admin_policy_a,
    library_a,
) -> None:
    """Uploading a TXT with PDF type/mime is rejected by signature checks."""
    url = reverse("resource-list", kwargs={"library_pk": str(library_a.pk)})
    response = client_a.post(
        url,
        {
            "name": "Fake PDF",
            "resource_type": ResourceType.PDF,
            "file": BytesIO(b"not a pdf"),
        },
        format="multipart",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "file" in response.data


@pytest.mark.django_db
def test_client_library_id_cannot_bypass_authorization(
    admin_client_a: APIClient,
    library_b,
) -> None:
    """A client cannot use a different library path to bypass authorization."""
    url = reverse("resource-list", kwargs={"library_pk": str(library_b.pk)})
    response = admin_client_a.post(
        url,
        _upload_payload("Cross", ResourceType.TXT, "cross.txt", b"data", "text/plain"),
        format="multipart",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert Resource.objects.count() == 0
