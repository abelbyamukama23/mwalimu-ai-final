"""Cryptographically secure OTP generation, hashing, and verification service."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.utils import timezone

from platform_api.apps.users.models import EmailOTP, EmailOTPPurpose

if TYPE_CHECKING:
    from platform_api.apps.users.models import User

logger = logging.getLogger(__name__)

OTP_EXPIRY_MINUTES = 10
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_ATTEMPTS = 5


class OTPError(Exception):
    """Base exception for OTP-related errors."""


class ResendCooldownError(OTPError):
    """Raised when an OTP is requested before the cooldown period expires."""

    def __init__(self, seconds_remaining: int) -> None:
        self.seconds_remaining = seconds_remaining
        super().__init__(
            f"You can request another code in {seconds_remaining} seconds."
        )


def _hash_otp(email: str, purpose: str, raw_otp: str) -> str:
    """Generate a deterministic SHA-256 digest using settings.SECRET_KEY as salt."""
    salt = getattr(settings, "SECRET_KEY", "mwalimu-otp-salt")
    normalized_email = email.strip().lower()
    raw_bytes = f"{salt}:{normalized_email}:{purpose}:{raw_otp}".encode()
    return hashlib.sha256(raw_bytes).hexdigest()


def generate_otp(
    email: str,
    purpose: str = EmailOTPPurpose.EMAIL_VERIFICATION,
    user: User | None = None,
) -> tuple[str, EmailOTP]:
    """Generate 6-digit OTP, save cryptographic hash, and enforce cooldown.

    Returns:
        tuple[str, EmailOTP]: The raw 6-digit OTP (for email dispatch ONLY)
                              and the persisted EmailOTP model instance.

    Raises:
        ResendCooldownError: If a previous unexpired OTP was created less than 60s ago.
        ValueError: If purpose is invalid or email is empty.
    """
    if not email:
        raise ValueError("Email address cannot be empty.")

    normalized_email = email.strip().lower()

    if purpose not in EmailOTPPurpose.values:
        raise ValueError(f"Invalid OTP purpose: '{purpose}'")

    now = timezone.now()

    # Enforce 60-second resend cooldown against the most recent active OTP
    recent_otp = (
        EmailOTP.objects.filter(
            email=normalized_email,
            purpose=purpose,
            is_used=False,
            expires_at__gt=now,
        )
        .order_by("-created_at")
        .first()
    )

    if recent_otp and now < recent_otp.resend_available_at:
        seconds_remaining = max(
            1, int((recent_otp.resend_available_at - now).total_seconds())
        )
        raise ResendCooldownError(seconds_remaining=seconds_remaining)

    # Invalidate any previously active unused OTPs for this email and purpose
    EmailOTP.objects.filter(
        email=normalized_email,
        purpose=purpose,
        is_used=False,
    ).update(is_used=True)

    # Generate cryptographically secure 6-digit numeric string
    raw_code = f"{secrets.randbelow(1_000_000):06d}"
    otp_hash = _hash_otp(normalized_email, purpose, raw_code)

    otp_record = EmailOTP.objects.create(
        user=user,
        email=normalized_email,
        otp_hash=otp_hash,
        purpose=purpose,
        expires_at=now + timedelta(minutes=OTP_EXPIRY_MINUTES),
        resend_available_at=now + timedelta(seconds=OTP_RESEND_COOLDOWN_SECONDS),
        attempts=0,
        is_used=False,
        created_at=now,
    )

    # Note: raw_code is returned ONLY to pass to email service.
    # It must NEVER be logged or persisted anywhere.
    return raw_code, otp_record



def verify_otp(
    email: str,
    purpose: str,
    raw_otp: str,
) -> tuple[bool, str, EmailOTP | None]:
    """Verify a raw 6-digit OTP against the active hashed record.

    Returns:
        tuple[bool, str, EmailOTP | None]:
            - success (True/False)
            - user-facing message
            - verified EmailOTP instance or None
    """
    if not email or not raw_otp:
        return False, "Email and verification code are required.", None

    normalized_email = email.strip().lower()
    clean_otp = raw_otp.strip()

    now = timezone.now()

    active_otp = (
        EmailOTP.objects.filter(
            email=normalized_email,
            purpose=purpose,
            is_used=False,
        )
        .order_by("-created_at")
        .first()
    )

    if not active_otp:
        return (
            False,
            "No active verification code found. Please request a new code.",
            None,
        )

    if now > active_otp.expires_at:
        active_otp.is_used = True
        active_otp.save(update_fields=["is_used"])
        return False, "That code has expired. Please request a new one.", None

    if active_otp.attempts >= OTP_MAX_ATTEMPTS:
        active_otp.is_used = True
        active_otp.save(update_fields=["is_used"])
        return False, "Too many failed attempts. Please request a new code.", None

    expected_hash = _hash_otp(normalized_email, purpose, clean_otp)

    # Constant-time comparison to prevent timing attacks
    if secrets.compare_digest(active_otp.otp_hash, expected_hash):
        active_otp.is_used = True
        active_otp.save(update_fields=["is_used"])
        return True, "Verification successful.", active_otp

    # Increment attempts on failure
    active_otp.attempts += 1
    if active_otp.attempts >= OTP_MAX_ATTEMPTS:
        active_otp.is_used = True
        active_otp.save(update_fields=["attempts", "is_used"])
        return False, "Too many failed attempts. Please request a new code.", None

    active_otp.save(update_fields=["attempts"])
    remaining = OTP_MAX_ATTEMPTS - active_otp.attempts
    attempt_str = f"{remaining} attempt{'s' if remaining != 1 else ''} remaining"
    return False, f"That code isn't correct. {attempt_str}.", None
