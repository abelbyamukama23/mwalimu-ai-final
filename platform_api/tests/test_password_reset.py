"""Tests for neutral password reset requests and OTP confirmation."""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from platform_api.apps.users.models import EmailOTP, EmailOTPPurpose
from platform_api.apps.users.services import otp_service

User = get_user_model()


@pytest.mark.django_db
@patch("platform_api.apps.users.services.email_service.send_password_reset_otp_email")
def test_password_reset_request_neutral_for_nonexistent_user(mock_send) -> None:
    """Password reset request returns neutral message when user does not exist."""
    client = APIClient()
    response = client.post(
        "/api/v1/auth/password-reset/request/",
        {"email": "nonexistent@example.com"},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert "If an account exists" in response.data["message"]
    mock_send.assert_not_called()
    assert EmailOTP.objects.filter(email="nonexistent@example.com").count() == 0


@pytest.mark.django_db
@patch("platform_api.apps.users.services.email_service.send_password_reset_otp_email")
def test_password_reset_request_sends_email_for_existing_user(mock_send) -> None:
    """Password reset request sends email and creates OTP for existing user."""
    user = User.objects.create_user(
        email="existing@example.com",
        password="OldPassword123!",
        is_email_verified=True,
    )

    client = APIClient()
    response = client.post(
        "/api/v1/auth/password-reset/request/",
        {"email": user.email},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert "If an account exists" in response.data["message"]
    mock_send.assert_called_once()
    assert (
        EmailOTP.objects.filter(
            email=user.email, purpose=EmailOTPPurpose.PASSWORD_RESET
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_password_reset_confirm_successful() -> None:
    """Confirming reset with valid OTP updates the password and allows login."""

    user = User.objects.create_user(
        email="resetme@example.com",
        password="OldPassword123!",
        is_email_verified=True,
    )
    raw_otp, _ = otp_service.generate_otp(
        user.email,
        purpose=EmailOTPPurpose.PASSWORD_RESET,
        user=user,
    )

    client = APIClient()
    response = client.post(
        "/api/v1/auth/password-reset/confirm/",
        {
            "email": user.email,
            "otp": raw_otp,
            "new_password": "BrandNewPassword123!",
            "new_password_confirm": "BrandNewPassword123!",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert "successfully reset" in response.data["message"].lower()

    # Verify old password no longer works
    login_old = client.post(
        "/api/v1/auth/login/",
        {"email": user.email, "password": "OldPassword123!"},
        format="json",
    )
    assert login_old.status_code == status.HTTP_401_UNAUTHORIZED

    # Verify new password works
    login_new = client.post(
        "/api/v1/auth/login/",
        {"email": user.email, "password": "BrandNewPassword123!"},
        format="json",
    )
    assert login_new.status_code == status.HTTP_200_OK
    assert "access" in login_new.data
