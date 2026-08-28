"""Tests for Google Drive connector adapter."""

from __future__ import annotations

import httpx
import pytest

from platform_api.apps.connectors.adapters.google_drive import GoogleDriveAdapter
from platform_api.apps.connectors.models import (
    Connection,
    ConnectionSyncJob,
    Connector,
    ConnectorAuthType,
    ConnectorType,
    SyncJobStatus,
)
from platform_api.apps.institutions.models import Institution
from platform_api.apps.libraries.models import Library
from platform_api.apps.resources.models import Resource, ResourceType
from platform_api.apps.users.models import User


@pytest.fixture
def institution(db: None) -> Institution:
    return Institution.objects.create(name="Drive Uni", slug="drive-uni")


@pytest.fixture
def user(db: None, institution: Institution) -> User:
    return User.objects.create_user(email="prof@drive.edu", password="ValidPass123!")


@pytest.fixture
def library(db: None, institution: Institution) -> Library:
    return Library.objects.create(institution=institution, name="GDrive Lib", slug="gdrive-lib")


@pytest.fixture
def gdrive_connector(db: None) -> Connector:
    connector, _ = Connector.objects.update_or_create(
        slug="google-drive",
        defaults={
            "name": "Google Drive",
            "connector_type": ConnectorType.GOOGLE_DRIVE,
            "auth_type": ConnectorAuthType.OAUTH2,
            "config_schema": {
                "type": "object",
                "properties": {"folder_id": {"type": "string"}},
                "required": ["folder_id"],
            },
            "auth_schema": {
                "type": "object",
                "properties": {"oauth_token": {"type": "string"}},
                "required": ["oauth_token"],
            },
            "is_active": True,
        },
    )
    return connector


@pytest.mark.django_db
def test_google_drive_sync_files_and_export(
    library: Library,
    gdrive_connector: Connector,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Google Drive adapter discovers files, downloads and exports Docs, and triggers processing."""
    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "files?q=" in url_str:
            # File list response
            data = {
                "files": [
                    {
                        "id": "doc123",
                        "name": "Syllabus 2026",
                        "mimeType": "application/vnd.google-apps.document",
                    },
                    {
                        "id": "pdf456",
                        "name": "Lecture1.pdf",
                        "mimeType": "application/pdf",
                    },
                ]
            }
            return httpx.Response(200, json=data)
        elif "files/doc123/export" in url_str:
            return httpx.Response(200, text="Course Syllabus: CS 101\nWeek 1: Intro")
        elif "files/pdf456?alt=media" in url_str:
            return httpx.Response(200, content=b"%PDF-1.4 Mock PDF Stream Data")
        return httpx.Response(404)

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = GoogleDriveAdapter(http_client=mock_client)

    enqueued: list[Resource] = []
    monkeypatch.setattr(
        "platform_api.apps.connectors.adapters.google_drive.enqueue_processing",
        lambda r: enqueued.append(r),
    )

    connection = Connection.objects.create(
        library=library,
        connector=gdrive_connector,
        name="Course Drive",
        configuration={"folder_id": "folder_abc"},
        created_by=user,
    )
    connection.set_credentials({"oauth_token": "ya29.mock-token"})
    connection.save()

    sync_job = ConnectionSyncJob.objects.create(connection=connection)

    result = adapter.sync(connection, sync_job)

    assert result.is_success is True
    assert result.resources_discovered == 2
    assert result.resources_created == 2
    assert len(enqueued) == 2

    # Verify Resource instances
    txt_res = Resource.objects.get(library=library, original_filename="gdrive_doc123.txt")
    assert txt_res.resource_type == ResourceType.TXT
    assert txt_res.name == "[GDrive] Syllabus 2026"

    pdf_res = Resource.objects.get(library=library, original_filename="gdrive_pdf456.pdf")
    assert pdf_res.resource_type == ResourceType.PDF
    assert pdf_res.name == "[GDrive] Lecture1.pdf"
