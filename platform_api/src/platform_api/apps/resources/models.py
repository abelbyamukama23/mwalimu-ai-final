"""Resource model for the Mwalimu Platform API."""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from platform_api.apps.libraries.models import Library


class ResourceType(models.TextChoices):
    """Supported resource types for the MVP."""

    PDF = "pdf", "PDF"
    DOCX = "docx", "DOCX"
    TXT = "txt", "Text"


class ResourceStatus(models.TextChoices):
    """Lifecycle statuses for a resource.

    These states describe the resource itself, not the future knowledge-
    processing pipeline (chunking, extraction, embeddings).
    """

    PENDING = "pending", "Pending"
    UPLOADING = "uploading", "Uploading"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"
    ARCHIVED = "archived", "Archived"


class Resource(models.Model):
    """A knowledge resource owned by a library.

    Resource metadata lives in PostgreSQL. The original binary is stored in
    S3-compatible object storage and is never persisted in the database.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    library = models.ForeignKey(
        Library,
        on_delete=models.CASCADE,
        related_name="resources",
    )
    name = models.CharField(max_length=255)
    resource_type = models.CharField(
        max_length=20,
        choices=ResourceType.choices,
        db_index=True,
    )
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=255)
    size = models.PositiveBigIntegerField()
    object_key = models.CharField(
        max_length=512,
        unique=True,
        db_index=True,
    )
    checksum = models.CharField(
        max_length=64,
        help_text="SHA-256 hex digest of the original content.",
    )
    status = models.CharField(
        max_length=20,
        choices=ResourceStatus.choices,
        default=ResourceStatus.PENDING,
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="resources",
    )

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata."""

        db_table = "resources_resource"
        ordering = ["-created_at"]
        verbose_name = "resource"
        verbose_name_plural = "resources"

    def __str__(self) -> str:
        """Return the resource name."""
        return self.name
