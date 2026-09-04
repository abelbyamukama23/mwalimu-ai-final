"""Institution model for the Mwalimu Platform API."""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class InstitutionStatus(models.TextChoices):
    """Lifecycle statuses for an institution."""

    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    ARCHIVED = "archived", "Archived"


class InstitutionType(models.TextChoices):
    """Classification of organizational learning workspaces."""

    FAMILY = "family", "Family"
    SCHOOL = "school", "School (K-12)"
    COLLEGE = "college", "College / Vocational Institute"
    UNIVERSITY = "university", "University / Higher Education"
    TRAINING_CENTER = "training_center", "Training Center / Academy"
    EDUCATION_ORGANIZATION = (
        "education_organization",
        "Educational Organization / NGO",
    )
    OTHER = "other", "Other Organization"


class Institution(models.Model):
    """An institutional tenant in the Mwalimu platform."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=InstitutionStatus.choices,
        default=InstitutionStatus.ACTIVE,
        db_index=True,
    )
    institution_type = models.CharField(
        max_length=30,
        choices=InstitutionType.choices,
        default=InstitutionType.SCHOOL,
        db_index=True,
        help_text="The organizational classification of this learning workspace.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_institutions",
        help_text="User who originally established this institution workspace.",
    )
    logo_object_key = models.CharField(
        max_length=512,
        blank=True,
        default="",
        help_text="Object storage key for the institutional badge/logo.",
    )
    logo_content_type = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="MIME content type of the stored logo (e.g. image/png).",
    )
    logo_updated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the branding logo was last modified.",
    )

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata."""

        db_table = "institutions_institution"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["slug"],
                name="institutions_institution_slug_unique",
                violation_error_message="An institution with this slug already exists.",
            ),
        ]
        verbose_name = "institution"
        verbose_name_plural = "institutions"

    def __str__(self) -> str:
        """Return the institution name."""
        return self.name


class AuditAction(models.TextChoices):
    """Enumeration of audited administrative actions."""

    # Memberships
    MEMBER_ROLE_CHANGED = "member.role_changed", "Member Role Changed"
    MEMBER_STATUS_CHANGED = "member.status_changed", "Member Status Changed"
    MEMBER_REMOVED = "member.removed", "Member Removed"

    # Libraries
    LIBRARY_CREATED = "library.created", "Library Created"
    LIBRARY_UPDATED = "library.updated", "Library Updated"
    LIBRARY_DELETED = "library.deleted", "Library Deleted"

    # Library Invitations
    INVITATION_CREATED = "library.invitation_created", "Library Invitation Created"
    INVITATION_REVOKED = "library.invitation_revoked", "Library Invitation Revoked"
    INVITATION_ACCEPTED = "library.invitation_accepted", "Library Invitation Accepted"
    INVITATION_DECLINED = "library.invitation_declined", "Library Invitation Declined"

    # Access Policies
    ACCESS_GRANTED = "access.granted", "Access Policy Granted"
    ACCESS_UPDATED = "access.updated", "Access Policy Updated"
    ACCESS_REVOKED = "access.revoked", "Access Policy Revoked"

    # Resources
    RESOURCE_UPLOADED = "resource.uploaded", "Resource Uploaded"
    RESOURCE_DELETED = "resource.deleted", "Resource Deleted"
    RESOURCE_REINDEXED = "resource.reindexed", "Resource Reindexed"

    # Connections
    CONNECTION_CREATED = "connection.created", "Connection Created"
    CONNECTION_UPDATED = "connection.updated", "Connection Updated"
    CONNECTION_DELETED = "connection.deleted", "Connection Deleted"
    CONNECTION_SYNC_TRIGGERED = "connection.sync_triggered", "Sync Triggered"

    # Institution
    INSTITUTION_UPDATED = "institution.updated", "Institution Settings Updated"
    BRANDING_UPDATED = "institution.branding_updated", "Branding Updated"


class InstitutionalAuditEvent(models.Model):
    """Immutable, append-only ledger of administrative actions for an institution."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name="audit_events",
        db_index=True,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_actions",
    )
    action = models.CharField(max_length=50, choices=AuditAction.choices, db_index=True)
    target_type = models.CharField(max_length=50, db_index=True)
    target_id = models.CharField(max_length=255, blank=True, default="")
    target_repr = models.CharField(max_length=255)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)

    class Meta:
        """Model metadata."""

        db_table = "institutions_audit_event"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["institution", "-created_at"]),
            models.Index(fields=["institution", "action"]),
        ]
        verbose_name = "institutional audit event"
        verbose_name_plural = "institutional audit events"

    def save(self, *args: object, **kwargs: object) -> None:
        """Enforce append-only immutability."""
        from django.core.exceptions import ValidationError

        if not self._state.adding:
            raise ValidationError("Audit events are strictly immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> tuple[int, dict[str, int]]:
        """Block deletion of audit events."""
        from django.core.exceptions import ValidationError

        raise ValidationError("Audit events are strictly immutable and cannot be deleted.")

    def __str__(self) -> str:
        """Human-readable string representation."""
        actor_email = self.actor.email if self.actor else "system"
        return f"{self.created_at.isoformat()} | {self.action} by {actor_email} on {self.target_repr}"
