"""Tests for Google OAuth 2.0 / OpenID Connect authorization and linking."""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from platform_api.apps.users.services import google_auth_service

User = get_user_model()


@pytest.mark.django_db
def test_google_auth_url_generation() -> None:
    """GET /api/v1/auth/google/url/ returns auth URL and valid signed state."""
    client = APIClient()
    response = client.get("/api/v1/auth/google/url/")

    assert response.status_code == status.HTTP_200_OK
    assert "url" in response.data
    assert "state" in response.data

    decoded = google_auth_service.decode_google_oauth_state(response.data["state"])
    assert "redirect_uri" in decoded


@pytest.mark.django_db
def test_google_auth_callback_invalid_state_rejected() -> None:
    """Invalid or tampered state tokens are rejected with 400."""
    client = APIClient()
    response = client.post(
        "/api/v1/auth/google/callback/",
        {
            "code": "any_code",
            "state": "tampered_fake_state",
            "redirect_uri": "http://localhost:3000/auth/google/callback",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "error" in response.data


@pytest.mark.django_db
@patch(
    "platform_api.apps.users.services.google_auth_service.exchange_google_code_and_get_identity"
)
def test_google_auth_callback_creates_new_verified_user(mock_exchange) -> None:
    """New Google user creates verified user and profile."""
    state = google_auth_service.generate_google_oauth_state(
        "http://localhost:3000/auth/google/callback"
    )
    mock_exchange.return_value = {
        "sub": "google_sub_unique_123",
        "email": "new.google.learner@example.com",
        "email_verified": True,
        "name": "Dr. Sarah",
        "picture": "https://example.com/avatar.jpg",
    }

    client = APIClient()
    response = client.post(
        "/api/v1/auth/google/callback/",
        {
            "code": "valid_auth_code",
            "state": state,
            "redirect_uri": "http://localhost:3000/auth/google/callback",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert "access" in response.data
    assert response.data["user"]["email"] == "new.google.learner@example.com"
    assert response.data["user"]["is_email_verified"] is True

    user = User.objects.get(email="new.google.learner@example.com")
    assert user.google_sub == "google_sub_unique_123"
    assert user.is_email_verified is True
    assert user.profile.display_name == "Dr. Sarah"
    assert user.profile.avatar_url == "https://example.com/avatar.jpg"


@pytest.mark.django_db
@patch(
    "platform_api.apps.users.services.google_auth_service.exchange_google_code_and_get_identity"
)
def test_google_auth_callback_links_existing_user(mock_exchange) -> None:
    """Existing user with matching email links Google sub and verifies email."""


    existing_user = User.objects.create_user(
        email="existing.learner@example.com",
        password="Password123!",
        is_email_verified=False,
    )
    from platform_api.apps.users.models import UserProfile

    UserProfile.objects.create(user=existing_user, display_name="Original Name")

    state = google_auth_service.generate_google_oauth_state(
        "http://localhost:3000/auth/google/callback"
    )
    mock_exchange.return_value = {
        "sub": "google_sub_linked_456",
        "email": "existing.learner@example.com",
        "email_verified": True,
        "name": "Google Name",
        "picture": "",
    }

    client = APIClient()
    response = client.post(
        "/api/v1/auth/google/callback/",
        {
            "code": "valid_auth_code",
            "state": state,
            "redirect_uri": "http://localhost:3000/auth/google/callback",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert "access" in response.data

    existing_user.refresh_from_db()
    assert existing_user.google_sub == "google_sub_linked_456"
    assert existing_user.is_email_verified is True
    # Preserves customized profile display name
    assert existing_user.profile.display_name == "Original Name"
