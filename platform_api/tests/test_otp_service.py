"""Tests for OTP Service (generation, hashing, expiration, cooldown, and limits)."""

from datetime import timedelta

import pytest
from django.utils import timezone

from platform_api.apps.users.models import EmailOTPPurpose
from platform_api.apps.users.services import otp_service
from platform_api.apps.users.services.otp_service import ResendCooldownError


@pytest.mark.django_db
def test_otp_generation_and_hashing() -> None:
    """OTP is 6 digits and stored as a SHA-256 hash, never plaintext."""
    email = "learner@example.com"
    raw_otp, record = otp_service.generate_otp(
        email, purpose=EmailOTPPurpose.EMAIL_VERIFICATION
    )

    assert len(raw_otp) == 6
    assert raw_otp.isdigit()
    assert record.email == email
    assert record.purpose == EmailOTPPurpose.EMAIL_VERIFICATION
    assert record.is_used is False
    assert record.attempts == 0

    # Ensure plaintext OTP is NOT in database
    assert raw_otp != record.otp_hash
    assert len(record.otp_hash) == 64  # SHA-256 hex length


@pytest.mark.django_db
def test_otp_successful_verification() -> None:
    """Correct OTP verifies and is marked as used."""
    email = "learner@example.com"
    raw_otp, record = otp_service.generate_otp(
        email, purpose=EmailOTPPurpose.EMAIL_VERIFICATION
    )

    success, msg, verified = otp_service.verify_otp(
        email, EmailOTPPurpose.EMAIL_VERIFICATION, raw_otp
    )

    assert success is True
    assert "successful" in msg.lower()
    assert verified is not None
    assert verified.id == record.id

    record.refresh_from_db()
    assert record.is_used is True


@pytest.mark.django_db
def test_otp_single_use() -> None:
    """An OTP cannot be reused once verified."""
    email = "learner@example.com"
    raw_otp, _ = otp_service.generate_otp(
        email, purpose=EmailOTPPurpose.EMAIL_VERIFICATION
    )

    # First verification
    success1, _, _ = otp_service.verify_otp(
        email, EmailOTPPurpose.EMAIL_VERIFICATION, raw_otp
    )
    assert success1 is True

    # Second verification fails
    success2, msg2, _ = otp_service.verify_otp(
        email, EmailOTPPurpose.EMAIL_VERIFICATION, raw_otp
    )
    assert success2 is False
    assert "no active" in msg2.lower()


@pytest.mark.django_db
def test_otp_expiration() -> None:
    """Expired OTPs are rejected and invalidated."""
    email = "learner@example.com"
    raw_otp, record = otp_service.generate_otp(
        email, purpose=EmailOTPPurpose.EMAIL_VERIFICATION
    )

    # Simulate expiration (11 minutes ago)
    record.expires_at = timezone.now() - timedelta(minutes=1)
    record.save(update_fields=["expires_at"])

    success, msg, _ = otp_service.verify_otp(
        email, EmailOTPPurpose.EMAIL_VERIFICATION, raw_otp
    )
    assert success is False
    assert "expired" in msg.lower()

    record.refresh_from_db()
    assert record.is_used is True


@pytest.mark.django_db
def test_otp_five_attempt_limit() -> None:
    """5 failed attempts invalidates the OTP."""
    email = "learner@example.com"
    raw_otp, record = otp_service.generate_otp(
        email, purpose=EmailOTPPurpose.EMAIL_VERIFICATION
    )

    # 4 incorrect attempts
    for i in range(1, 5):
        success, msg, _ = otp_service.verify_otp(
            email, EmailOTPPurpose.EMAIL_VERIFICATION, "000000"
        )
        assert success is False
        remaining = 5 - i
        assert f"{remaining} attempt" in msg

    # 5th incorrect attempt invalidates
    success, msg, _ = otp_service.verify_otp(
        email, EmailOTPPurpose.EMAIL_VERIFICATION, "000000"
    )
    assert success is False
    assert "too many failed attempts" in msg.lower()

    record.refresh_from_db()
    assert record.is_used is True
    assert record.attempts == 5

    # Subsequent attempt even with correct OTP fails
    success_after, _, _ = otp_service.verify_otp(
        email, EmailOTPPurpose.EMAIL_VERIFICATION, raw_otp
    )
    assert success_after is False


@pytest.mark.django_db
def test_otp_resend_cooldown() -> None:
    """Requesting a new OTP before 60 seconds raises ResendCooldownError."""
    email = "cooldown@example.com"
    otp_service.generate_otp(email, purpose=EmailOTPPurpose.EMAIL_VERIFICATION)

    with pytest.raises(ResendCooldownError) as exc_info:
        otp_service.generate_otp(email, purpose=EmailOTPPurpose.EMAIL_VERIFICATION)

    assert exc_info.value.seconds_remaining <= 60


@pytest.mark.django_db
def test_otp_invalidates_previous_active_otps() -> None:
    """Generating a new OTP invalidates previous active OTPs for email and purpose."""

    email = "replace@example.com"
    raw1, record1 = otp_service.generate_otp(
        email, purpose=EmailOTPPurpose.EMAIL_VERIFICATION
    )

    # Fast forward cooldown
    record1.resend_available_at = timezone.now() - timedelta(seconds=1)
    record1.save(update_fields=["resend_available_at"])

    raw2, record2 = otp_service.generate_otp(
        email, purpose=EmailOTPPurpose.EMAIL_VERIFICATION
    )

    record1.refresh_from_db()
    assert record1.is_used is True
    assert record2.is_used is False

    # Old code fails
    success1, _, _ = otp_service.verify_otp(
        email, EmailOTPPurpose.EMAIL_VERIFICATION, raw1
    )
    assert success1 is False

    # New code succeeds
    success2, _, _ = otp_service.verify_otp(
        email, EmailOTPPurpose.EMAIL_VERIFICATION, raw2
    )
    assert success2 is True
