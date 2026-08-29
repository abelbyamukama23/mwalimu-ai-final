"""Tests for registration, email OTP verification, cooldown, and welcome emails."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from platform_api.apps.users.models import EmailOTP, EmailOTPPurpose
from platform_api.apps.users.services import otp_service

User = get_user_model()


@pytest.mark.django_db
@patch("platform_api.apps.users.services.email_service.send_verification_otp_email")
def test_registration_creates_unverified_user_and_dispatches_otp(
    mock_send_email,
) -> None:
    """Registration creates is_email_verified=False and triggers OTP dispatch."""
    client = APIClient()
    payload = {
        "email": "newlearner@example.com",
        "password": "StrongPassword123!",
        "password_confirm": "StrongPassword123!",
    }

    response = client.post("/api/v1/auth/register/", payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["email"] == "newlearner@example.com"
    assert response.data["requires_verification"] is True

    user = User.objects.get(email="newlearner@example.com")
    assert user.is_email_verified is False
    assert user.email_verified_at is None

    mock_send_email.assert_called_once()
    assert mock_send_email.call_args[0][0] == "newlearner@example.com"

    # Verify OTP record in database is hashed
    otp_record = EmailOTP.objects.filter(email="newlearner@example.com").first()
    assert otp_record is not None
    assert otp_record.is_used is False


@pytest.mark.django_db
@patch("platform_api.apps.users.services.email_service.send_welcome_email")
def test_verify_email_with_valid_otp(mock_welcome_email) -> None:
    """Verifying with correct OTP verifies user, sets display name, and sends email."""

    user = User.objects.create_user(
        email="learner@example.com",
        password="StrongPassword123!",
        is_email_verified=False,
    )
    raw_otp, _ = otp_service.generate_otp(
        user.email, purpose=EmailOTPPurpose.EMAIL_VERIFICATION, user=user
    )

    client = APIClient()
    response = client.post(
        "/api/v1/auth/verify-email/",
        {
            "email": "learner@example.com",
            "otp": raw_otp,
            "display_name": "Teacher Abel",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert "access" in response.data
    assert response.data["user"]["email"] == "learner@example.com"
    assert response.data["user"]["is_email_verified"] is True

    user.refresh_from_db()
    assert user.is_email_verified is True
    assert user.email_verified_at is not None
    assert user.profile.display_name == "Teacher Abel"

    mock_welcome_email.assert_called_once_with("learner@example.com", "Teacher Abel")


@pytest.mark.django_db
def test_verify_email_with_invalid_otp() -> None:
    """Invalid OTP returns 400 error."""
    user = User.objects.create_user(
        email="learner@example.com",
        password="StrongPassword123!",
        is_email_verified=False,
    )
    otp_service.generate_otp(
        user.email, purpose=EmailOTPPurpose.EMAIL_VERIFICATION, user=user
    )

    client = APIClient()
    response = client.post(
        "/api/v1/auth/verify-email/",
        {
            "email": "learner@example.com",
            "otp": "999999",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "error" in response.data

    user.refresh_from_db()
    assert user.is_email_verified is False


@pytest.mark.django_db
@patch("platform_api.apps.users.services.email_service.send_verification_otp_email")
def test_resend_otp_enforces_cooldown(mock_send) -> None:
    """Resend enforces 60-second cooldown and returns 429 when too soon."""
    user = User.objects.create_user(
        email="learner@example.com",
        password="StrongPassword123!",
        is_email_verified=False,
    )
    otp_service.generate_otp(
        user.email, purpose=EmailOTPPurpose.EMAIL_VERIFICATION, user=user
    )

    client = APIClient()
    # 1. Immediate resend -> 429
    resp1 = client.post(
        "/api/v1/auth/resend-otp/",
        {"email": "learner@example.com", "purpose": "email_verification"},
        format="json",
    )
    assert resp1.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    # 2. Fast-forward cooldown
    active_otp = EmailOTP.objects.filter(email="learner@example.com").first()
    assert active_otp is not None
    active_otp.resend_available_at = timezone.now() - timedelta(seconds=2)
    active_otp.save(update_fields=["resend_available_at"])

    # 3. Resend allowed
    resp2 = client.post(
        "/api/v1/auth/resend-otp/",
        {"email": "learner@example.com", "purpose": "email_verification"},
        format="json",
    )
    assert resp2.status_code == status.HTTP_200_OK
    assert "sent" in resp2.data["message"].lower()
