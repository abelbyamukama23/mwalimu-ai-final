"""Library and access-policy models for the Mwalimu Platform API."""

import uuid
from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone

from platform_api.apps.institutions.models import Institution


class LibraryScopeType(models.TextChoices):
    """Ownership scope for a library."""

    PERSONAL = "personal", "Personal"
    INSTITUTION = "institution", "Institution"


class LibraryStatus(models.TextChoices):
    """Lifecycle statuses for a library."""

    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"


class LibraryVisibility(models.TextChoices):
    """Discovery settings for a library.

    A discoverable library may be listed for members of its institution, but
    discovery does not grant management or resource authorization. Restricted
    libraries are only visible to users with an explicit access policy.
    """

    DISCOVERABLE = "discoverable", "Discoverable"
    RESTRICTED = "restricted", "Restricted"


class LibraryAccessRole(models.TextChoices):
    """Roles granted by an explicit library access policy."""

    ADMINISTRATOR = "administrator", "Administrator"
    TEACHER = "teacher", "Teacher"
    STUDENT = "student", "Student"


class Library(models.Model):
    """A logical knowledge and security boundary for a user or an institution.

    Personal libraries are owned directly by a user. Institutional libraries
    belong to an institution and are managed by institution administrators.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scope_type = models.CharField(
        max_length=20,
        choices=LibraryScopeType.choices,
        default=LibraryScopeType.PERSONAL,
        db_index=True,
    )
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name="libraries",
        null=True,
        blank=True,
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="personal_libraries",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=LibraryStatus.choices,
        default=LibraryStatus.ACTIVE,
        db_index=True,
    )
    visibility = models.CharField(
        max_length=20,
        choices=LibraryVisibility.choices,
        default=LibraryVisibility.RESTRICTED,
        db_index=True,
    )

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata."""

        db_table = "libraries_library"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["owner", "-created_at"],
                name="lib_owner_created_idx",
            ),
            models.Index(
                fields=["institution", "-created_at"],
                name="lib_inst_created_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        scope_type=LibraryScopeType.PERSONAL,
                        owner__isnull=False,
                        institution__isnull=True,
                    )
                    | models.Q(
                        scope_type=LibraryScopeType.INSTITUTION,
                        institution__isnull=False,
                        owner__isnull=True,
                    )
                ),
                name="libraries_library_ownership_valid",
                violation_error_message=(
                    "A personal library must have an owner and no institution; "
                    "an institutional library must have an institution and no owner."
                ),
            ),
            models.UniqueConstraint(
                fields=["institution", "slug"],
                condition=models.Q(scope_type=LibraryScopeType.INSTITUTION),
                name="libraries_library_institution_slug_unique",
                violation_error_message=(
                    "A library with this slug already exists in this institution."
                ),
            ),
            models.UniqueConstraint(
                fields=["owner", "slug"],
                condition=models.Q(scope_type=LibraryScopeType.PERSONAL),
                name="libraries_library_owner_slug_unique",
                violation_error_message=(
                    "You already have a personal library with this slug."
                ),
            ),
        ]
        verbose_name = "library"
        verbose_name_plural = "libraries"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Derive scope_type if unambiguous and save instance."""
        if self.institution_id is not None and self.owner_id is None:
            self.scope_type = LibraryScopeType.INSTITUTION
        elif self.owner_id is not None and self.institution_id is None:
            self.scope_type = LibraryScopeType.PERSONAL
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        """Return the library name."""
        return self.name


class LibraryAccessPolicy(models.Model):
    """Explicit authorization grant for a user on a library.

    Institution membership alone does not imply library access. Each grant is
    scoped to one library and one user. Institution administrators manage
    libraries without requiring a separate policy row.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    library = models.ForeignKey(
        Library,
        on_delete=models.CASCADE,
        related_name="access_policies",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="library_access_policies",
    )
    role = models.CharField(
        max_length=20,
        choices=LibraryAccessRole.choices,
        default=LibraryAccessRole.STUDENT,
        db_index=True,
    )

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata."""

        db_table = "libraries_accesspolicy"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["library", "user"],
                name="libraries_accesspolicy_user_library_unique",
                violation_error_message=(
                    "This user already has an access policy for this library."
                ),
            ),
        ]
        verbose_name = "library access policy"
        verbose_name_plural = "library access policies"

    def __str__(self) -> str:
        """Return a human-readable policy description."""
        return f"{self.user.email} @ {self.library.name} ({self.role})"
