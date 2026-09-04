"""Tests for Institutional Branding & Badge management."""

from io import BytesIO
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient

from platform_api.apps.institutions.models import AuditAction, Institution, InstitutionalAuditEvent
from platform_api.apps.memberships.models import Membership, MembershipRole, MembershipStatus
from platform_api.apps.resources.fake_storage import FakeStorage
from platform_api.apps.users.models import User


@pytest.fixture(autouse=True)
def _clear_storage():
    """Ensure clean fake storage for each test."""
    FakeStorage.clear()
    yield
    FakeStorage.clear()


@pytest.mark.django_db
class TestInstitutionalBranding:
    """Test suite for institutional badge/logo lifecycle and authorization."""

    def test_admin_can_upload_and_replace_badge(self):
        """Institution admin may upload an image badge."""
        admin_user = User.objects.create_user(email="admin@school.edu", password="password123")
        institution = Institution.objects.create(name="Greenwood Academy", slug="greenwood")
        Membership.objects.create(
            user=admin_user,
            institution=institution,
            role=MembershipRole.ADMINISTRATOR,
            status=MembershipStatus.ACTIVE,
        )

        client = APIClient()
        client.force_authenticate(user=admin_user)

        # 1. Upload valid PNG badge
        png_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
        uploaded_file = SimpleUploadedFile("badge.png", png_content, content_type="image/png")

        res = client.post(
            f"/api/v1/institutions/{institution.id}/branding/",
            {"file": uploaded_file},
            format="multipart",
        )
        assert res.status_code == status.HTTP_200_OK
        institution.refresh_from_db()
        assert institution.logo_object_key.startswith(f"institutions/{institution.id}/branding/")
        assert institution.logo_content_type == "image/png"
        assert res.data.get("badge_url") is not None
        assert f"/api/v1/institutions/{institution.id}/badge/" in res.data["badge_url"]

        # Audit event recorded
        audit = InstitutionalAuditEvent.objects.filter(
            institution=institution, action=AuditAction.BRANDING_UPDATED
        ).first()
        assert audit is not None
        assert audit.metadata.get("event") == "badge_uploaded"

        # 2. Replace with JPEG badge
        jpeg_content = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb"
        replaced_file = SimpleUploadedFile("badge.jpg", jpeg_content, content_type="image/jpeg")

        res2 = client.post(
            f"/api/v1/institutions/{institution.id}/branding/",
            {"file": replaced_file},
            format="multipart",
        )
        assert res2.status_code == status.HTTP_200_OK
        institution.refresh_from_db()
        assert institution.logo_content_type == "image/jpeg"

    def test_non_admin_cannot_modify_branding(self):
        """Student or general member cannot upload or delete branding."""
        student = User.objects.create_user(email="student@school.edu", password="password123")
        institution = Institution.objects.create(name="Greenwood Academy", slug="greenwood")
        Membership.objects.create(
            user=student,
            institution=institution,
            role=MembershipRole.STUDENT,
            status=MembershipStatus.ACTIVE,
        )

        client = APIClient()
        client.force_authenticate(user=student)

        png_content = b"\x89PNG\r\n\x1a\n"
        uploaded_file = SimpleUploadedFile("badge.png", png_content, content_type="image/png")

        res = client.post(
            f"/api/v1/institutions/{institution.id}/branding/",
            {"file": uploaded_file},
            format="multipart",
        )
        assert res.status_code == status.HTTP_403_FORBIDDEN

        res_del = client.delete(f"/api/v1/institutions/{institution.id}/branding/")
        assert res_del.status_code == status.HTTP_403_FORBIDDEN

    def test_reject_unsupported_file_format(self):
        """Uploading non-image files must be rejected with HTTP 400."""
        admin_user = User.objects.create_user(email="admin@school.edu", password="password123")
        institution = Institution.objects.create(name="Greenwood Academy", slug="greenwood")
        Membership.objects.create(
            user=admin_user,
            institution=institution,
            role=MembershipRole.ADMINISTRATOR,
            status=MembershipStatus.ACTIVE,
        )

        client = APIClient()
        client.force_authenticate(user=admin_user)

        txt_file = SimpleUploadedFile("script.sh", b"#!/bin/bash echo hello", content_type="text/plain")
        res = client.post(
            f"/api/v1/institutions/{institution.id}/branding/",
            {"file": txt_file},
            format="multipart",
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "Unsupported image type" in str(res.data)

    def test_admin_can_remove_branding(self):
        """Admin may remove the badge logo."""
        admin_user = User.objects.create_user(email="admin@school.edu", password="password123")
        institution = Institution.objects.create(
            name="Greenwood Academy",
            slug="greenwood",
            logo_object_key="institutions/fake/branding/logo.png",
            logo_content_type="image/png",
        )
        Membership.objects.create(
            user=admin_user,
            institution=institution,
            role=MembershipRole.ADMINISTRATOR,
            status=MembershipStatus.ACTIVE,
        )

        client = APIClient()
        client.force_authenticate(user=admin_user)

        res = client.delete(f"/api/v1/institutions/{institution.id}/branding/")
        assert res.status_code == status.HTTP_204_NO_CONTENT
        institution.refresh_from_db()
        assert institution.logo_object_key == ""
        assert institution.logo_content_type == ""

    def test_stream_badge_endpoint(self):
        """Public streaming endpoint serves badge with proper cache headers."""
        institution = Institution.objects.create(
            name="Greenwood Academy",
            slug="greenwood",
        )
        storage = FakeStorage()
        key = f"institutions/{institution.id}/branding/test_badge.png"
        sample_png = b"\x89PNG\r\n\x1a\nsample_data"
        storage.upload(key, BytesIO(sample_png), content_type="image/png", size=len(sample_png))

        institution.logo_object_key = key
        institution.logo_content_type = "image/png"
        institution.save()

        client = APIClient()
        res = client.get(f"/api/v1/institutions/{institution.id}/badge/")
        assert res.status_code == status.HTTP_200_OK
        assert res["Content-Type"] == "image/png"
        assert "public" in res["Cache-Control"]
        assert b"".join(res.streaming_content) == sample_png
