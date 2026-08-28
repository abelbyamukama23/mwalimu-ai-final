"""Tests for OAuth 2.0 authorization and callback views."""

from __future__ import annotations

import httpx
import pytest
from rest_framework.test import APIClient

from platform_api.apps.connectors.models import (
    Connection,
    Connector,
    ConnectorAuthType,
    ConnectorType,
)
from platform_api.apps.connectors.oauth import generate_oauth_state
from platform_api.apps.institutions.models import Institution
from platform_api.apps.libraries.models import Library
from platform_api.apps.memberships.models import Membership, MembershipRole, MembershipStatus
from platform_api.apps.users.models import User


@pytest.fixture
def institution(db: None) -> Institution:
    return Institution.objects.create(name="OAuth Uni", slug="oauth-uni")


@pytest.fixture
def user_admin(db: None, institution: Institution) -> User:
    user = User.objects.create_user(email="admin@oauth.edu", password="ValidPass123!")
    Membership.objects.create(
        user=user,
        institution=institution,
        role=MembershipRole.ADMINISTRATOR,
        status=MembershipStatus.ACTIVE,
    )
    return user


@pytest.fixture
def library(db: None, institution: Institution) -> Library:
    return Library.objects.create(institution=institution, name="OAuth Lib", slug="oauth-lib")


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
def test_oauth_authorize_view_generates_url(
    user_admin: User, library: Library
) -> None:
    """Authenticated manager can request an OAuth authorization URL."""
    client = APIClient()
    client.force_authenticate(user=user_admin)

    resp = client.get(
        f"/api/v1/libraries/{library.id}/connections/oauth/google/authorize/"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "google"
    assert "https://accounts.google.com/o/oauth2/v2/auth" in data["authorization_url"]
    assert "state=" in data["authorization_url"]


@pytest.mark.django_db
def test_oauth_callback_view_exchanges_tokens_and_creates_connection(
    user_admin: User,
    library: Library,
    gdrive_connector: Connector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OAuth callback validates signed state and saves connection with encrypted credentials."""
    state = generate_oauth_state("google", library.id, user_admin.id)

    def mock_exchange(provider: str, code: str, redirect_uri: str, **kwargs: object) -> dict[str, str]:
        return {
            "oauth_token": "ya29.test_access_token",
            "refresh_token": "1//test_refresh_token",
        }

    monkeypatch.setattr(
        "platform_api.apps.connectors.oauth.exchange_oauth_code",
        mock_exchange,
    )

    client = APIClient()
    resp = client.get(
        f"/api/v1/connectors/oauth/google/callback/?code=mock_auth_code&state={state}"
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Google Connection"
    assert data["has_credentials"] is True

    # Verify encrypted in database
    conn = Connection.objects.get(id=data["id"])
    assert conn.get_credentials() == {
        "oauth_token": "ya29.test_access_token",
        "refresh_token": "1//test_refresh_token",
    }
