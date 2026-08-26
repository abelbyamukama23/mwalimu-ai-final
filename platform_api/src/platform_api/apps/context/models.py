"""Data models for Mwalimu context domain.

Models defined here:
- GeographicUnit: hierarchical geographic entity (country, region, district, etc.).
- ContextDomain: classification category (agriculture, climate, society, etc.).
- ContextResource: curated pedagogical context snippet.
- UserFamiliarRegion: user-configured familiar geographic area with priority rank.
- InstitutionContextRegion: institution-configured contextual focus region.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

# ---------------------------------------------------------------------------
# Normalization Helpers
# ---------------------------------------------------------------------------


def normalize_tags(raw_tags: list[str] | Any) -> list[str]:
    """Normalize a list of tag strings: lowercase, trimmed, deduplicated, non-empty."""
    if not isinstance(raw_tags, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_tags:
        if isinstance(item, str):
            cleaned = item.strip().lower()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                normalized.append(cleaned)
    return normalized


# ---------------------------------------------------------------------------
# Choice Enumerations
# ---------------------------------------------------------------------------


class GeographicUnitType(models.TextChoices):
    """Types of geographic units in the administrative hierarchy."""

    COUNTRY = "country", "Country"
    REGION = "region", "Region"
    DISTRICT = "district", "District"
    COUNTY = "county", "County"
    SUBCOUNTY = "subcounty", "Subcounty"
    PARISH = "parish", "Parish"
    VILLAGE = "village", "Village"
    CITY = "city", "City"
    TOWN = "town", "Town"
    OTHER = "other", "Other"


class GeographicUnitStatus(models.TextChoices):
    """Lifecycle statuses for geographic units."""

    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"


class ContextScopeType(models.TextChoices):
    """Scope of a context resource."""

    PLATFORM = "platform", "Platform Canonical"
    INSTITUTION = "institution", "Institution Custom"


class ContextResourceStatus(models.TextChoices):
    """Lifecycle statuses for context resources."""

    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"


class PedagogicalPurpose(models.TextChoices):
    """Permitted educational purposes for a context snippet."""

    EXAMPLE = "example", "Example"
    EXPLANATION = "explanation", "Explanation"
    ACTIVITY = "activity", "Activity"
    ASSESSMENT = "assessment", "Assessment"
    ANALOGY = "analogy", "Analogy"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class GeographicUnit(models.Model):
    """Hierarchical geographic reference unit for pedagogical context.

    Uses self-referential ForeignKey with PROTECT deletion semantics.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, db_index=True)
    unit_type = models.CharField(
        max_length=30,
        choices=GeographicUnitType.choices,
        default=GeographicUnitType.DISTRICT,
        db_index=True,
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )
    country_code = models.CharField(
        max_length=2,
        blank=True,
        default="",
        db_index=True,
        help_text="ISO 3166-1 alpha-2 code e.g. UG.",
    )
    status = models.CharField(
        max_length=20,
        choices=GeographicUnitStatus.choices,
        default=GeographicUnitStatus.ACTIVE,
        db_index=True,
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Arbitrary geographic metadata (e.g. alternate names, coordinates).",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata."""

        db_table = "context_geographic_unit"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "slug"],
                name="context_geounit_parent_slug_unique",
                violation_error_message=(
                    "A geographic unit with this slug already exists under this parent."
                ),
            ),
            models.UniqueConstraint(
                fields=["slug"],
                condition=models.Q(parent__isnull=True),
                name="context_geounit_root_slug_unique",
                violation_error_message=(
                    "A root geographic unit with this slug already exists."
                ),
            ),
        ]
        verbose_name = "geographic unit"
        verbose_name_plural = "geographic units"

    def __str__(self) -> str:
        """Return human-readable representation."""
        if self.parent:
            return f"{self.name} ({self.unit_type}, in {self.parent.name})"
        return f"{self.name} ({self.unit_type})"

    def clean(self) -> None:
        """Validate hierarchical integrity and cycle prevention."""
        super().clean()
        if self.parent_id and self.parent_id == self.id:
            raise ValidationError(
                {"parent": "A geographic unit cannot be its own parent."}
            )

        # Detect cycles by ascending parent hierarchy
        visited = {self.id} if self.id else set()
        current = self.parent
        while current is not None:
            if current.id in visited:
                raise ValidationError(
                    {"parent": "Hierarchy cycle detected in parent chain."}
                )
            visited.add(current.id)
            current = current.parent


class ContextDomain(models.Model):
    """Categorical domain classification for context resources."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata."""

        db_table = "context_domain"
        ordering = ["name"]
        verbose_name = "context domain"
        verbose_name_plural = "context domains"

    def __str__(self) -> str:
        """Return domain name."""
        return self.name


class ContextResource(models.Model):
    """Curated educational contextual knowledge snippet attached to a geographic unit.

    Maximum content length is 5,000 characters.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    geographic_unit = models.ForeignKey(
        GeographicUnit,
        on_delete=models.PROTECT,
        related_name="context_resources",
    )
    context_domain = models.ForeignKey(
        ContextDomain,
        on_delete=models.PROTECT,
        related_name="context_resources",
    )
    title = models.CharField(max_length=255)
    content = models.TextField(
        max_length=5000,
        help_text="Concise educational contextual knowledge snippet (max 5000 chars).",
    )
    scope_type = models.CharField(
        max_length=20,
        choices=ContextScopeType.choices,
        default=ContextScopeType.PLATFORM,
        db_index=True,
    )
    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="context_resources",
        help_text="Populated when scope_type is INSTITUTION.",
    )
    source_reference = models.CharField(
        max_length=512,
        blank=True,
        default="",
        help_text="Citation or provenance reference.",
    )
    status = models.CharField(
        max_length=20,
        choices=ContextResourceStatus.choices,
        default=ContextResourceStatus.ACTIVE,
        db_index=True,
    )

    # Normalized pedagogical applicability tags
    applicable_subjects = models.JSONField(
        default=list,
        blank=True,
        help_text="List of school subjects (e.g. ['biology', 'agriculture']).",
    )
    applicable_topics = models.JSONField(
        default=list,
        blank=True,
        help_text="List of curriculum topics (e.g. ['photosynthesis']).",
    )
    pedagogical_purposes = models.JSONField(
        default=list,
        blank=True,
        help_text="List of pedagogical purposes (e.g. ['example', 'explanation']).",
    )
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata."""

        db_table = "context_resource"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["geographic_unit", "status"]),
            models.Index(fields=["context_domain", "status"]),
            models.Index(fields=["scope_type", "institution"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(scope_type=ContextScopeType.PLATFORM)
                        & models.Q(institution__isnull=True)
                    )
                    | (
                        models.Q(scope_type=ContextScopeType.INSTITUTION)
                        & models.Q(institution__isnull=False)
                    )
                ),
                name="context_resource_scope_institution_integrity",
                violation_error_message=(
                    "Platform resources must not specify an institution; "
                    "Institution resources must specify an institution."
                ),
            ),
        ]
        verbose_name = "context resource"
        verbose_name_plural = "context resources"

    def __str__(self) -> str:
        """Return resource title and unit."""
        return f"{self.title} ({self.geographic_unit.name})"

    def clean(self) -> None:
        """Validate content length, scope alignment, geographic unit, and purposes."""
        super().clean()

        # 1. Content length check
        if self.content and len(self.content) > 5000:
            raise ValidationError({"content": "Content cannot exceed 5000 characters."})

        # 2. Scope vs institution validation
        if (
            self.scope_type == ContextScopeType.PLATFORM
            and self.institution_id is not None
        ):
            raise ValidationError(
                {
                    "institution": (
                        "Platform context resources must not be linked "
                        "to an institution."
                    )
                }
            )
        if (
            self.scope_type == ContextScopeType.INSTITUTION
            and self.institution_id is None
        ):
            raise ValidationError(
                {
                    "institution": (
                        "Institution context resources must be linked "
                        "to an institution."
                    )
                }
            )

        # 3. Geographic unit active status check
        if (
            self.geographic_unit_id
            and hasattr(self, "geographic_unit")
            and self.geographic_unit.status != GeographicUnitStatus.ACTIVE
        ):
            raise ValidationError(
                {
                    "geographic_unit": (
                        "Cannot attach context resources to an archived "
                        "geographic unit."
                    )
                }
            )

        # 4. Normalize tags
        self.applicable_subjects = normalize_tags(self.applicable_subjects)
        self.applicable_topics = normalize_tags(self.applicable_topics)

        # 5. Validate and normalize pedagogical purposes
        normalized_purposes = normalize_tags(self.pedagogical_purposes)
        valid_purposes = set(PedagogicalPurpose.values)
        for purpose in normalized_purposes:
            if purpose not in valid_purposes:
                raise ValidationError(
                    {
                        "pedagogical_purposes": (
                            f"Invalid pedagogical purpose '{purpose}'. "
                            f"Valid choices are: {sorted(valid_purposes)}."
                        )
                    }
                )
        self.pedagogical_purposes = normalized_purposes


class UserFamiliarRegion(models.Model):
    """User-configured familiar geographic area with priority rank.

    Familiar regions represent geographic areas whose examples, practices,
    and environmental references are cognitively familiar to the learner/teacher.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="familiar_regions",
    )
    geographic_unit = models.ForeignKey(
        GeographicUnit,
        on_delete=models.CASCADE,
        related_name="user_familiar_regions",
    )
    priority = models.PositiveSmallIntegerField(
        default=1,
        help_text="Priority rank: 1 is highest priority familiarity.",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata."""

        db_table = "context_user_familiar_region"
        ordering = ["priority", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "geographic_unit"],
                name="context_user_familiar_unit_unique",
                violation_error_message=(
                    "This geographic unit is already in your familiar regions."
                ),
            ),
        ]
        verbose_name = "user familiar region"
        verbose_name_plural = "user familiar regions"

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.user} - {self.geographic_unit.name} (Priority {self.priority})"

    def clean(self) -> None:
        """Validate priority and active geographic unit."""
        super().clean()
        if self.priority < 1:
            raise ValidationError(
                {"priority": "Priority must be greater than or equal to 1."}
            )

        if (
            self.geographic_unit_id
            and hasattr(self, "geographic_unit")
            and self.geographic_unit.status != GeographicUnitStatus.ACTIVE
        ):
            raise ValidationError(
                {
                    "geographic_unit": (
                        "Cannot select an archived geographic unit as a "
                        "familiar region."
                    )
                }
            )


class InstitutionContextRegion(models.Model):
    """Institution-configured context region focus with priority rank.

    Represents geographical focus areas relevant to an institution's student
    population (e.g. district catchment area or regional scope).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="context_regions",
    )
    geographic_unit = models.ForeignKey(
        GeographicUnit,
        on_delete=models.CASCADE,
        related_name="institution_context_regions",
    )
    priority = models.PositiveSmallIntegerField(
        default=1,
        help_text="Priority rank: 1 is highest priority focus region.",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata."""

        db_table = "context_institution_region"
        ordering = ["priority", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["institution", "geographic_unit"],
                name="context_inst_region_unit_unique",
                violation_error_message=(
                    "This geographic unit is already configured for this institution."
                ),
            ),
        ]
        verbose_name = "institution context region"
        verbose_name_plural = "institution context regions"

    def __str__(self) -> str:
        """Return string representation."""
        return (
            f"{self.institution.name} - "
            f"{self.geographic_unit.name} (Priority {self.priority})"
        )

    def clean(self) -> None:
        """Validate priority and active geographic unit."""
        super().clean()
        if self.priority < 1:
            raise ValidationError(
                {"priority": "Priority must be greater than or equal to 1."}
            )

        if (
            self.geographic_unit_id
            and hasattr(self, "geographic_unit")
            and self.geographic_unit.status != GeographicUnitStatus.ACTIVE
        ):
            raise ValidationError(
                {
                    "geographic_unit": (
                        "Cannot select an archived geographic unit as an "
                        "institution context region."
                    )
                }
            )
