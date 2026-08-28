"""Tests for AWS S3 connector adapter."""

from __future__ import annotations

import io
from unittest.mock import MagicMock
import pytest

from platform_api.apps.connectors.adapters.s3 import S3Adapter
from platform_api.apps.connectors.models import (
    Connection,
    ConnectionSyncJob,
    Connector,
    ConnectorAuthType,
    ConnectorType,
)
from platform_api.apps.institutions.models import Institution
from platform_api.apps.libraries.models import Library
from platform_api.apps.resources.models import Resource, ResourceType
from platform_api.apps.users.models import User


@pytest.fixture
def institution(db: None) -> Institution:
    return Institution.objects.create(name="S3 Uni", slug="s3-uni")


@pytest.fixture
def user(db: None, institution: Institution) -> User:
    return User.objects.create_user(email="s3admin@uni.edu", password="ValidPass123!")


@pytest.fixture
def library(db: None, institution: Institution) -> Library:
    return Library.objects.create(institution=institution, name="S3 Lib", slug="s3-lib")


@pytest.fixture
def s3_connector(db: None) -> Connector:
    connector, _ = Connector.objects.update_or_create(
        slug="amazon-s3",
        defaults={
            "name": "Amazon S3",
            "connector_type": ConnectorType.S3,
            "auth_type": ConnectorAuthType.BASIC_AUTH,
            "config_schema": {
                "type": "object",
                "properties": {"bucket_name": {"type": "string"}},
                "required": ["bucket_name"],
            },
            "auth_schema": {
                "type": "object",
                "properties": {
                    "aws_access_key_id": {"type": "string"},
                    "aws_secret_access_key": {"type": "string"},
                },
                "required": ["aws_access_key_id", "aws_secret_access_key"],
            },
            "is_active": True,
        },
    )
    return connector


@pytest.mark.django_db
def test_s3_sync_bucket_objects(
    library: Library,
    s3_connector: Connector,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S3 adapter lists bucket objects, downloads files, and indexes library resources."""
    mock_s3 = MagicMock()
    mock_paginator = MagicMock()
    mock_s3.get_paginator.return_value = mock_paginator
    mock_paginator.paginate.return_value = [
        {
            "Contents": [
                {"Key": "course_files/syllabus.pdf"},
                {"Key": "course_files/notes.txt"},
                {"Key": "course_files/image.png"},  # Ignored format
            ]
        }
    ]

    def mock_get_object(Bucket: str, Key: str) -> dict[str, Any]:
        if Key.endswith(".pdf"):
            return {"Body": io.BytesIO(b"%PDF-1.4 Mock S3 PDF content")}
        return {"Body": io.BytesIO(b"Course notes content in plain text")}

    mock_s3.get_object.side_effect = mock_get_object

    adapter = S3Adapter(s3_client=mock_s3)

    enqueued: list[Resource] = []
    monkeypatch.setattr(
        "platform_api.apps.connectors.adapters.s3.enqueue_processing",
        lambda r: enqueued.append(r),
    )

    connection = Connection.objects.create(
        library=library,
        connector=s3_connector,
        name="Course S3 Bucket",
        configuration={"bucket_name": "mwalimu-course-bucket", "prefix": "course_files/"},
        created_by=user,
    )
    connection.set_credentials(
        {"aws_access_key_id": "AKIA123", "aws_secret_access_key": "secret456"}
    )
    connection.save()

    sync_job = ConnectionSyncJob.objects.create(connection=connection)

    result = adapter.sync(connection, sync_job)

    assert result.is_success is True
    assert result.resources_discovered == 2  # image.png was skipped
    assert result.resources_created == 2
    assert len(enqueued) == 2

    pdf_res = Resource.objects.filter(library=library, resource_type=ResourceType.PDF).first()
    assert pdf_res is not None
    assert "[S3] syllabus.pdf" in pdf_res.name

    txt_res = Resource.objects.filter(library=library, resource_type=ResourceType.TXT).first()
    assert txt_res is not None
    assert "[S3] notes.txt" in txt_res.name
