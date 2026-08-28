"""Tests for Remote File Browser API endpoint."""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest
from rest_framework.test import APIClient

from platform_api.apps.connectors.models import (
    Connection,
    Connector,
    ConnectorAuthType,
    ConnectorType,
)
from platform_api.apps.institutions.models import Institution
from platform_api.apps.libraries.models import Library
from platform_api.apps.memberships.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
)
from platform_api.apps.users.models import User


@pytest.fixture
def institution(db: None) -> Institution:
    return Institution.objects.create(name="Browser Uni", slug="browser-uni")


@pytest.fixture
def user_admin(db: None, institution: Institution) -> User:
    user = User.objects.create_user(email="admin@browser.edu", password="ValidPass123!")
    Membership.objects.create(
        user=user,
        institution=institution,
        role=MembershipRole.ADMINISTRATOR,
        status=MembershipStatus.ACTIVE,
    )
    return user


@pytest.fixture
def user_student(db: None, institution: Institution) -> User:
    user = User.objects.create_user(email="student@browser.edu", password="ValidPass123!")
    Membership.objects.create(
        user=user,
        institution=institution,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.ACTIVE,
    )
    return user


@pytest.fixture
def library(db: None, institution: Institution) -> Library:
    return Library.objects.create(institution=institution, name="Browser Lib", slug="browser-lib")


@pytest.fixture
def gdrive_connector(db: None) -> Connector:
    connector, _ = Connector.objects.update_or_create(
        slug="google-drive",
        defaults={
            "name": "Google Drive",
            "connector_type": ConnectorType.GOOGLE_DRIVE,
            "auth_type": ConnectorAuthType.OAUTH2,
            "is_active": True,
        },
    )
    return connector


@pytest.mark.django_db
def test_remote_browser_api_manager_success(
    user_admin: User,
    library: Library,
    gdrive_connector: Connector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manager can browse remote connection files."""
    connection = Connection.objects.create(
        library=library,
        connector=gdrive_connector,
        name="Drive Link",
        created_by=user_admin,
    )
    connection.set_credentials({"oauth_token": "ya29.mock_token"})
    connection.save()

    mock_adapter = MagicMock()
    mock_adapter.browse.return_value = {
        "current_folder_id": "root",
        "breadcrumbs": [{"id": "root", "name": "My Drive"}],
        "items": [
            {"id": "f1", "name": "Course Materials", "type": "folder"},
            {"id": "d1", "name": "Syllabus.pdf", "type": "file", "size": 1024},
        ],
    }

    monkeypatch.setattr(
        "platform_api.apps.connectors.views_browser.get_connector_adapter",
        lambda _: mock_adapter,
    )

    client = APIClient()
    client.force_authenticate(user=user_admin)

    resp = client.get(
        f"/api/v1/libraries/{library.id}/connections/{connection.id}/browse/?folder_id=root"
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["items"][0]["name"] == "Course Materials"
    assert data["items"][1]["name"] == "Syllabus.pdf"


@pytest.mark.django_db
def test_remote_browser_api_student_rejected(
    user_student: User,
    library: Library,
    gdrive_connector: Connector,
) -> None:
    """Non-manager members are rejected from browsing connection credentials/files."""
    connection = Connection.objects.create(
        library=library,
        connector=gdrive_connector,
        name="Drive Link",
        created_by=user_student,
    )

    client = APIClient()
    client.force_authenticate(user=user_student)

    resp = client.get(
        f"/api/v1/libraries/{library.id}/connections/{connection.id}/browse/"
    )
    assert resp.status_code == 403
