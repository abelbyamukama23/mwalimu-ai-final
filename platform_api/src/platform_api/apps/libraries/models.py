"""Library and access-policy models for the Mwalimu Platform API."""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from platform_api.apps.institutions.models import Institution


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
    """A logical knowledge and security boundary within an institution.

    Libraries share platform infrastructure and are isolated through
    institution and library-level authorization rather than separate databases
    or deployments.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name="libraries",
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
        constraints = [
            models.UniqueConstraint(
                fields=["institution", "slug"],
                name="libraries_library_institution_slug_unique",
                violation_error_message=(
                    "A library with this slug already exists in this institution."
                ),
            ),
        ]
        verbose_name = "library"
        verbose_name_plural = "libraries"

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
