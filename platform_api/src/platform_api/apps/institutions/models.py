"""Institution model for the Mwalimu Platform API."""

import uuid

from django.db import models
from django.utils import timezone


class InstitutionStatus(models.TextChoices):
    """Lifecycle statuses for an institution."""

    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    ARCHIVED = "archived", "Archived"


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
