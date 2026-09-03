"""Membership model for the Mwalimu Platform API."""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from platform_api.apps.institutions.models import Institution


class MembershipRole(models.TextChoices):
    """Roles available within an institutional membership."""

    ADMINISTRATOR = "administrator", "Administrator"
    TEACHER = "teacher", "Teacher"
    STUDENT = "student", "Student"
    LIBRARIAN = "librarian", "Librarian"


class MembershipStatus(models.TextChoices):
    """Lifecycle statuses for a membership."""

    PENDING = "pending", "Pending"
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    SUSPENDED = "suspended", "Suspended"


class Membership(models.Model):
    """Relationship between a user and an institution."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(
        max_length=20,
        choices=MembershipRole.choices,
        default=MembershipRole.STUDENT,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=MembershipStatus.choices,
        default=MembershipStatus.ACTIVE,
        db_index=True,
    )

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata."""

        db_table = "memberships_membership"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "institution"],
                condition=models.Q(status=MembershipStatus.ACTIVE),
                name="memberships_membership_one_active_per_institution",
                violation_error_message=(
                    "This user already has an active membership for this institution."
                ),
            ),
        ]
        verbose_name = "membership"
        verbose_name_plural = "memberships"

    def __str__(self) -> str:
        """Return a human-readable membership description."""
        return f"{self.user.email} @ {self.institution.name} ({self.role})"

    def delete(self, *args: object, **kwargs: object) -> tuple[int, dict[str, int]]:
        """Prevent deleting the last active administrator of an institution."""
        if (
            self.role == MembershipRole.ADMINISTRATOR
            and self.status == MembershipStatus.ACTIVE
        ):
            active_admins = (
                Membership.objects.filter(
                    institution=self.institution,
                    role=MembershipRole.ADMINISTRATOR,
                    status=MembershipStatus.ACTIVE,
                )
                .exclude(pk=self.pk)
                .count()
            )
            if active_admins == 0:
                from django.core.exceptions import ValidationError

                raise ValidationError(
                    "Cannot delete the final active administrator of an institution."
                )
        return super().delete(*args, **kwargs)
