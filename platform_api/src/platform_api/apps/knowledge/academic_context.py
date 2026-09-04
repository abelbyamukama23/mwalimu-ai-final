"""Academic context resolution for context-aware knowledge retrieval."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from platform_api.apps.institutions.models import AcademicUnit
from platform_api.apps.libraries.models import Library, LibraryStatus, LibraryTargetType
from platform_api.apps.memberships.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
    TeachingAssignmentStatus,
)
from platform_api.apps.users.models import User


@dataclass(frozen=True)
class AcademicContextSummary:
    """Summary of the resolved academic context for a user."""

    institution_id: uuid.UUID | None
    role: str | None
    academic_unit_ids: frozenset[uuid.UUID]
    is_administrator: bool = False

    @property
    def has_academic_context(self) -> bool:
        """Return True if user has any academic units associated."""
        return len(self.academic_unit_ids) > 0


def resolve_academic_context(
    user: User,
    institution_id: uuid.UUID | None = None,
) -> AcademicContextSummary:
    """Resolve the active academic units and role for a user within an institution.

    - Students: Resolves to their placed academic unit.
    - Teachers: Resolves to all academic units they are actively assigned to teach.
    - Administrators: Resolves to all active academic units in the institution.
    - Non-institutional / Family / No Placement: Resolves to empty academic units.
    """
    if not getattr(user, "is_authenticated", False):
        return AcademicContextSummary(
            institution_id=None,
            role=None,
            academic_unit_ids=frozenset(),
        )

    try:
        membership_qs = Membership.objects.filter(
            user=user,
            status=MembershipStatus.ACTIVE,
        )
        if institution_id:
            membership_qs = membership_qs.filter(institution_id=institution_id)

        membership = membership_qs.first()
    except Exception:
        membership = None

    if not membership:
        return AcademicContextSummary(
            institution_id=institution_id,
            role=None,
            academic_unit_ids=frozenset(),
        )

    inst_id = membership.institution_id

    try:
        # 1. Administrator: has context across all active units in the institution
        if membership.role == MembershipRole.ADMINISTRATOR:
            all_units = AcademicUnit.objects.filter(
                institution_id=inst_id,
                is_active=True,
            ).values_list("id", flat=True)
            return AcademicContextSummary(
                institution_id=inst_id,
                role=membership.role,
                academic_unit_ids=frozenset(all_units),
                is_administrator=True,
            )

        # 2. Teacher: has context across all assigned academic units
        if membership.role == MembershipRole.TEACHER:
            assigned_units = membership.teaching_assignments.filter(
                status=TeachingAssignmentStatus.ACTIVE,
                academic_unit__is_active=True,
            ).values_list("academic_unit_id", flat=True)
            return AcademicContextSummary(
                institution_id=inst_id,
                role=membership.role,
                academic_unit_ids=frozenset(assigned_units),
            )

        # 3. Student: has context of their assigned academic unit
        if membership.role == MembershipRole.STUDENT and membership.academic_unit_id:
            if membership.academic_unit and membership.academic_unit.is_active:
                return AcademicContextSummary(
                    institution_id=inst_id,
                    role=membership.role,
                    academic_unit_ids=frozenset([membership.academic_unit_id]),
                )
    except Exception:
        pass

    return AcademicContextSummary(
        institution_id=inst_id,
        role=membership.role,
        academic_unit_ids=frozenset(),
    )


def filter_libraries_by_academic_context(
    authorized_library_ids: frozenset[uuid.UUID],
    academic_context: AcademicContextSummary,
) -> frozenset[uuid.UUID]:
    """Filter and prioritize authorized libraries based on academic context.

    CRITICAL INVARIANT:
    Academic context NEVER grants access to unauthorized libraries.
    It operates strictly on the subset of libraries the user is already
    authorized to retrieve (authorized_library_ids).

    Rule:
    - Universal utility libraries (target_type == UTILITY) are ALWAYS retained.
    - Academic unit targeted libraries (target_type == ACADEMIC_UNIT) are retained
      if their target unit is within the user's active academic context.
    - If user has no specific academic units (e.g. unassigned student),
      universal utility libraries + personal libraries are returned.
    """
    if not authorized_library_ids:
        return frozenset()

    try:
        libraries = Library.objects.filter(
            id__in=authorized_library_ids,
            status=LibraryStatus.ACTIVE,
        ).values("id", "target_type", "academic_unit_id")

        retained: set[uuid.UUID] = set()
        for lib in libraries:
            # Universal utilities and personal libraries are always retained
            if lib["target_type"] == LibraryTargetType.UTILITY or not lib["academic_unit_id"]:
                retained.add(lib["id"])
            # Academic-unit targeted libraries match if target is in user's academic context
            elif lib["academic_unit_id"] in academic_context.academic_unit_ids:
                retained.add(lib["id"])

        # If filtering would leave zero libraries but the user was authorized for some,
        # fall back to all authorized libraries so search fails open for knowledge
        # without violating security boundaries.
        return frozenset(retained) if retained else authorized_library_ids
    except Exception:
        return authorized_library_ids
