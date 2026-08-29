"""Tests for the registration endpoint (POST /api/v1/auth/register/).

Contract under test:
- Registration creates an unverified user account (`is_email_verified=False`),
  generates a 6-digit OTP, dispatches the email, and returns
  `{email, requires_verification, message}`.
- Duplicate emails, invalid emails, weak/mismatched passwords, and missing
  password confirmation are rejected.

- The email is normalized, the password is hashed, the double-submit CSRF cookie
  is established, and registration never creates institution membership or privilege.
"""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from platform_api.apps.institutions.models import Institution
from platform_api.apps.libraries.models import LibraryAccessPolicy
from platform_api.apps.memberships.models import Membership

REGISTER_URL = reverse("register")

CREDENTIALS = {
    "email": "new.user@example.com",
    "password": "register-password-123",
    "password_confirm": "register-password-123",
}


@pytest.mark.django_db
@patch("platform_api.apps.users.services.email_service.send_verification_otp_email")
def test_register_creates_unverified_user_and_dispatches_otp(
    mock_send_email,
    api_client: APIClient,
) -> None:
    response = api_client.post(REGISTER_URL, CREDENTIALS, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["email"] == "new.user@example.com"
    assert response.data["requires_verification"] is True

    user = get_user_model().objects.get(email="new.user@example.com")
    assert user.check_password(CREDENTIALS["password"])
    assert user.is_active is True
    assert user.is_email_verified is False
    assert user.is_staff is False
    assert user.is_superuser is False

    mock_send_email.assert_called_once()


@pytest.mark.django_db
def test_register_establishes_csrf_cookie(api_client: APIClient) -> None:
    response = api_client.post(REGISTER_URL, CREDENTIALS, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert api_client.cookies.get("csrftoken") is not None


@pytest.mark.django_db
def test_register_creates_memberless_user(
    api_client: APIClient,
    institution_a: Institution,
) -> None:
    response = api_client.post(REGISTER_URL, CREDENTIALS, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    user = get_user_model().objects.get(email="new.user@example.com")
    assert Membership.objects.filter(user=user).count() == 0
    assert LibraryAccessPolicy.objects.filter(user=user).count() == 0


@pytest.mark.django_db
def test_register_normalizes_email(api_client: APIClient) -> None:
    creds = {
        "email": "  New.User@Example.COM ",
        "password": CREDENTIALS["password"],
        "password_confirm": CREDENTIALS["password"],
    }
    response = api_client.post(REGISTER_URL, creds, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert (
        get_user_model().objects.get(email="new.user@example.com").email
        == "new.user@example.com"
    )


@pytest.mark.django_db
def test_register_rejects_duplicate_email(api_client: APIClient) -> None:
    api_client.post(REGISTER_URL, CREDENTIALS, format="json")

    response = api_client.post(REGISTER_URL, CREDENTIALS, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "email" in response.data


@pytest.mark.django_db
def test_register_rejects_short_password(api_client: APIClient) -> None:
    response = api_client.post(
        REGISTER_URL,
        {
            "email": "short.pass@example.com",
            "password": "short",
            "password_confirm": "short",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "password" in response.data


@pytest.mark.django_db
def test_register_rejects_invalid_email(api_client: APIClient) -> None:
    response = api_client.post(
        REGISTER_URL,
        {
            "email": "not-an-email",
            "password": CREDENTIALS["password"],
            "password_confirm": CREDENTIALS["password"],
        },
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "email" in response.data


@pytest.mark.django_db
def test_register_rejects_password_mismatch(api_client: APIClient) -> None:
    response = api_client.post(
        REGISTER_URL,
        {
            "email": "mismatch@example.com",
            "password": "register-password-123",
            "password_confirm": "a-different-123",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "password_confirm" in response.data


@pytest.mark.django_db
def test_register_rejects_missing_password_confirm(api_client: APIClient) -> None:
    response = api_client.post(
        REGISTER_URL,
        {"email": "no-confirm@example.com", "password": "register-password-123"},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "password_confirm" in response.data
