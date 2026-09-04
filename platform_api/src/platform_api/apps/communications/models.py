"""Models for generic notifications and transactional communication outbox."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from .intents import CommunicationCategory, CommunicationIntent


class Notification(models.Model):
    """A generic, recipient-facing in-platform notification.

    Used across the entire Mwalimu platform for library invitations, membership
    lifecycle events, system announcements, and user-to-user domain alerts.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        db_index=True,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acted_notifications",
    )
    notification_type = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Stable identifier e.g. library.invitation or membership.approved",
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured action & deep-link metadata (e.g. invitation_id, library_id).",
    )
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata."""

        db_table = "communications_notification"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "-created_at"]),
            models.Index(fields=["recipient", "is_read", "-created_at"]),
            models.Index(fields=["recipient", "notification_type"]),
        ]
        verbose_name = "notification"
        verbose_name_plural = "notifications"

    def __str__(self) -> str:
        """Return a readable representation."""
        return f"{self.recipient.email} - {self.notification_type} ({self.created_at.isoformat()})"

    def mark_as_read(self) -> None:
        """Mark this notification as read."""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at", "updated_at"])


class OutboxMessageStatus(models.TextChoices):
    """Lifecycle statuses for outbox messages."""

    PENDING = "pending", "Pending"
    SENT = "sent", "Sent"
    RETRYING = "retrying", "Retrying"
    FAILED = "failed", "Failed"


class OutboxMessage(models.Model):
    """Transactional outbox record for reliable external email/message delivery.

    Guarantees that domain transactions do not fail if SMTP or Resend is unavailable,
    and minimizes duplicate delivery via idempotency keys.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    intent = models.CharField(
        max_length=100,
        choices=CommunicationIntent.choices,
        db_index=True,
    )
    category = models.CharField(
        max_length=50,
        choices=CommunicationCategory.choices,
        db_index=True,
    )
    recipient_email = models.EmailField(db_index=True)
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outbox_messages",
    )
    subject = models.CharField(max_length=255)
    html_body = models.TextField()
    text_body = models.TextField(blank=True, default="")
    idempotency_key = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=OutboxMessageStatus.choices,
        default=OutboxMessageStatus.PENDING,
        db_index=True,
    )
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    external_reference = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata."""

        db_table = "communications_outbox_message"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["recipient_email", "-created_at"]),
        ]
        verbose_name = "outbox message"
        verbose_name_plural = "outbox messages"

    def __str__(self) -> str:
        """Return readable representation."""
        return f"{self.intent} -> {self.recipient_email} [{self.status}]"
