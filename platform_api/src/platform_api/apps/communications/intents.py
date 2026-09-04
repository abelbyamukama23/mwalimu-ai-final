"""Communication categories, intents, and delivery channel definitions."""

from __future__ import annotations

from enum import Enum
from typing import NamedTuple

from django.db import models


class CommunicationCategory(models.TextChoices):
    """Stable top-level categories for all platform communications."""

    AUTHENTICATION = "authentication", "Authentication"
    ACCOUNT = "account", "Account"
    INSTITUTION = "institution", "Institution"
    MEMBERSHIP = "membership", "Membership"
    LIBRARY = "library", "Library"
    SYSTEM = "system", "System"
    SECURITY = "security", "Security"


class CommunicationChannel(str, Enum):
    """Available delivery channels for communications."""

    IN_APP_NOTIFICATION = "in_app_notification"
    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    PUSH = "push"


class CommunicationIntent(models.TextChoices):
    """Stable identifiers for platform communication intents."""

    # Authentication & Account
    AUTH_EMAIL_VERIFICATION = "auth.email_verification", "Email Verification OTP"
    AUTH_PASSWORD_RESET = "auth.password_reset", "Password Reset OTP"
    AUTH_WELCOME = "auth.welcome", "Welcome New User"

    # Library Invitations
    LIBRARY_INVITATION_EXISTING_USER = (
        "library.invitation.existing_user",
        "Library Invitation (Existing User)",
    )
    LIBRARY_INVITATION_NEW_USER = (
        "library.invitation.new_user",
        "Library Invitation (New User)",
    )
    LIBRARY_INVITATION_ACCEPTED = (
        "library.invitation.accepted",
        "Library Invitation Accepted",
    )
    LIBRARY_INVITATION_DECLINED = (
        "library.invitation.declined",
        "Library Invitation Declined",
    )
    LIBRARY_INVITATION_REVOKED = (
        "library.invitation.revoked",
        "Library Invitation Revoked",
    )

    # Membership
    MEMBERSHIP_REQUESTED = "membership.requested", "Membership Requested"
    MEMBERSHIP_APPROVED = "membership.approved", "Membership Approved"
    MEMBERSHIP_SUSPENDED = "membership.suspended", "Membership Suspended"
    MEMBERSHIP_ROLE_UPDATED = "membership.role_updated", "Membership Role Updated"

    # System & Announcements
    SYSTEM_ANNOUNCEMENT = "system.announcement", "System Announcement"
    SECURITY_ALERT = "security.alert", "Security Alert"


class IntentMetadata(NamedTuple):
    """Configuration binding for a communication intent."""

    category: CommunicationCategory
    default_channels: tuple[CommunicationChannel, ...]
    notification_type: str | None = None


# Intent configuration registry
INTENT_REGISTRY: dict[CommunicationIntent, IntentMetadata] = {
    CommunicationIntent.AUTH_EMAIL_VERIFICATION: IntentMetadata(
        category=CommunicationCategory.AUTHENTICATION,
        default_channels=(CommunicationChannel.EMAIL,),
    ),
    CommunicationIntent.AUTH_PASSWORD_RESET: IntentMetadata(
        category=CommunicationCategory.AUTHENTICATION,
        default_channels=(CommunicationChannel.EMAIL,),
    ),
    CommunicationIntent.AUTH_WELCOME: IntentMetadata(
        category=CommunicationCategory.ACCOUNT,
        default_channels=(CommunicationChannel.EMAIL,),
    ),
    CommunicationIntent.LIBRARY_INVITATION_EXISTING_USER: IntentMetadata(
        category=CommunicationCategory.LIBRARY,
        default_channels=(
            CommunicationChannel.IN_APP_NOTIFICATION,
            CommunicationChannel.EMAIL,
        ),
        notification_type="library.invitation",
    ),
    CommunicationIntent.LIBRARY_INVITATION_NEW_USER: IntentMetadata(
        category=CommunicationCategory.LIBRARY,
        default_channels=(CommunicationChannel.EMAIL,),
    ),
    CommunicationIntent.LIBRARY_INVITATION_ACCEPTED: IntentMetadata(
        category=CommunicationCategory.LIBRARY,
        default_channels=(
            CommunicationChannel.IN_APP_NOTIFICATION,
            CommunicationChannel.EMAIL,
        ),
        notification_type="library.invitation.accepted",
    ),
    CommunicationIntent.LIBRARY_INVITATION_DECLINED: IntentMetadata(
        category=CommunicationCategory.LIBRARY,
        default_channels=(
            CommunicationChannel.IN_APP_NOTIFICATION,
        ),
        notification_type="library.invitation.declined",
    ),
    CommunicationIntent.LIBRARY_INVITATION_REVOKED: IntentMetadata(
        category=CommunicationCategory.LIBRARY,
        default_channels=(
            CommunicationChannel.IN_APP_NOTIFICATION,
        ),
        notification_type="library.invitation.revoked",
    ),
    CommunicationIntent.MEMBERSHIP_REQUESTED: IntentMetadata(
        category=CommunicationCategory.MEMBERSHIP,
        default_channels=(
            CommunicationChannel.IN_APP_NOTIFICATION,
            CommunicationChannel.EMAIL,
        ),
        notification_type="membership.requested",
    ),
    CommunicationIntent.MEMBERSHIP_APPROVED: IntentMetadata(
        category=CommunicationCategory.MEMBERSHIP,
        default_channels=(
            CommunicationChannel.IN_APP_NOTIFICATION,
            CommunicationChannel.EMAIL,
        ),
        notification_type="membership.approved",
    ),
    CommunicationIntent.MEMBERSHIP_SUSPENDED: IntentMetadata(
        category=CommunicationCategory.MEMBERSHIP,
        default_channels=(
            CommunicationChannel.IN_APP_NOTIFICATION,
            CommunicationChannel.EMAIL,
        ),
        notification_type="membership.suspended",
    ),
    CommunicationIntent.MEMBERSHIP_ROLE_UPDATED: IntentMetadata(
        category=CommunicationCategory.MEMBERSHIP,
        default_channels=(
            CommunicationChannel.IN_APP_NOTIFICATION,
        ),
        notification_type="membership.role_changed",
    ),
    CommunicationIntent.SYSTEM_ANNOUNCEMENT: IntentMetadata(
        category=CommunicationCategory.SYSTEM,
        default_channels=(
            CommunicationChannel.IN_APP_NOTIFICATION,
        ),
        notification_type="system.announcement",
    ),
    CommunicationIntent.SECURITY_ALERT: IntentMetadata(
        category=CommunicationCategory.SECURITY,
        default_channels=(
            CommunicationChannel.IN_APP_NOTIFICATION,
            CommunicationChannel.EMAIL,
        ),
        notification_type="security.alert",
    ),
}
