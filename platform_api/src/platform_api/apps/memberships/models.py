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
    academic_unit = models.ForeignKey(
        "institutions.AcademicUnit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_memberships",
        help_text="The academic unit (e.g. class/grade) this student is placed in.",
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

    def clean(self) -> None:
        """Validate academic unit belongs to the same institution."""
        super().clean()
        if self.academic_unit_id and self.academic_unit.institution_id != self.institution_id:
            from django.core.exceptions import ValidationError

            raise ValidationError(
                {"academic_unit": "Academic unit must belong to the same institution."}
            )

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


class TeachingAssignmentStatus(models.TextChoices):
    """Lifecycle statuses for a teaching assignment."""

    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"


class TeachingAssignment(models.Model):
    """Assignment linking a teacher to an academic unit with an optional subject specialization."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name="teaching_assignments",
        db_index=True,
    )
    membership = models.ForeignKey(
        Membership,
        on_delete=models.CASCADE,
        related_name="teaching_assignments",
        db_index=True,
    )
    academic_unit = models.ForeignKey(
        "institutions.AcademicUnit",
        on_delete=models.CASCADE,
        related_name="teaching_assignments",
        db_index=True,
    )
    subject = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Optional subject taught (e.g. Mathematics, Science).",
    )
    status = models.CharField(
        max_length=20,
        choices=TeachingAssignmentStatus.choices,
        default=TeachingAssignmentStatus.ACTIVE,
        db_index=True,
    )
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata."""

        db_table = "memberships_teachingassignment"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["membership", "academic_unit", "subject"],
                condition=models.Q(status=TeachingAssignmentStatus.ACTIVE),
                name="memberships_teachingassignment_unique_active",
                violation_error_message=(
                    "An active teaching assignment for this teacher, academic unit, and subject already exists."
                ),
            ),
        ]
        indexes = [
            models.Index(fields=["institution", "status"]),
            models.Index(fields=["academic_unit", "status"]),
        ]
        verbose_name = "teaching assignment"
        verbose_name_plural = "teaching assignments"

    def clean(self) -> None:
        """Enforce teacher role and tenant consistency."""
        super().clean()
        from django.core.exceptions import ValidationError

        if self.membership_id:
            if self.membership.role != MembershipRole.TEACHER:
                raise ValidationError(
                    {"membership": "Only members with the role 'teacher' can have teaching assignments."}
                )
            if self.institution_id and self.membership.institution_id != self.institution_id:
                raise ValidationError(
                    {"institution": "Teaching assignment institution must match member's institution."}
                )

        if self.academic_unit_id:
            if self.institution_id and self.academic_unit.institution_id != self.institution_id:
                raise ValidationError(
                    {"academic_unit": "Academic unit must belong to the same institution."}
                )

    def save(self, *args: object, **kwargs: object) -> None:
        """Ensure institution matches membership before saving."""
        if not self.institution_id and self.membership_id:
            self.institution_id = self.membership.institution_id
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        """Return human-readable representation."""
        sub = f" - {self.subject}" if self.subject else ""
        return f"{self.membership.user.email} -> {self.academic_unit.name}{sub} ({self.status})"
