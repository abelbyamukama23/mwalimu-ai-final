"""Tests for JWT authentication endpoints."""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_login_returns_tokens(user_a, api_client: APIClient) -> None:
    """A valid login returns access and refresh tokens."""
    url = reverse("token_obtain_pair")
    response = api_client.post(
        url,
        {"email": "user.a@example.com", "password": "password-a-123"},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert "access" in response.data
    assert "refresh" in response.data
    assert isinstance(response.data["access"], str)
    assert isinstance(response.data["refresh"], str)


@pytest.mark.django_db
def test_login_invalid_password(api_client: APIClient) -> None:
    """An invalid password returns 401 with no tokens."""
    url = reverse("token_obtain_pair")
    response = api_client.post(
        url,
        {"email": "user.a@example.com", "password": "wrong-password"},
        format="json",
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "access" not in response.data
    assert "refresh" not in response.data


@pytest.mark.django_db
def test_token_refresh(user_a, api_client: APIClient) -> None:
    """A valid refresh token returns a new access token."""
    login_url = reverse("token_obtain_pair")
    login_response = api_client.post(
        login_url,
        {"email": "user.a@example.com", "password": "password-a-123"},
        format="json",
    )
    refresh_token = login_response.data["refresh"]

    refresh_url = reverse("token_refresh")
    response = api_client.post(refresh_url, {"refresh": refresh_token}, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert "access" in response.data
    assert isinstance(response.data["access"], str)


@pytest.mark.django_db
def test_token_refresh_invalid(api_client: APIClient) -> None:
    """An invalid refresh token returns 401."""
    url = reverse("token_refresh")
    response = api_client.post(url, {"refresh": "not-a-real-token"}, format="json")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "access" not in response.data


@pytest.mark.django_db
def test_current_user_requires_authentication(api_client: APIClient) -> None:
    """The current-user endpoint rejects unauthenticated requests."""
    url = reverse("current_user")
    response = api_client.get(url)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_current_user_returns_profile(client_a, user_a) -> None:
    """An authenticated user receives their own profile."""
    url = reverse("current_user")
    response = client_a.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["email"] == user_a.email
    assert response.data["id"] == str(user_a.pk)
    assert "password" not in response.data
