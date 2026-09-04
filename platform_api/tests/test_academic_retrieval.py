"""Tests for Academic Context Resolution and Context-Aware Knowledge Retrieval."""

import uuid
import pytest

from platform_api.apps.institutions.models import (
    AcademicUnit,
    AcademicUnitType,
)
from platform_api.apps.knowledge.academic_context import (
    filter_libraries_by_academic_context,
    resolve_academic_context,
)
from platform_api.apps.knowledge.policies import (
    EffectiveRetrievalScope,
    KnowledgeAuthorizationPolicy,
)
from platform_api.apps.libraries.models import (
    Library,
    LibraryAccessPolicy,
    LibraryAccessRole,
    LibraryScopeType,
    LibraryStatus,
    LibraryTargetType,
    LibraryVisibility,
)
from platform_api.apps.memberships.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
    TeachingAssignment,
    TeachingAssignmentStatus,
)


@pytest.mark.django_db
def test_resolve_academic_context_student_teacher_admin(
    institution_a, user_a, user_b
) -> None:
    """Context resolver returns correct academic units by role."""
    unit_p4 = AcademicUnit.objects.create(
        institution=institution_a, name="Primary 4", code="P4", order=4
    )
    unit_p5 = AcademicUnit.objects.create(
        institution=institution_a, name="Primary 5", code="P5", order=5
    )

    # 1. Student placed in P4
    student_mem = Membership.objects.create(
        user=user_b,
        institution=institution_a,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.ACTIVE,
        academic_unit=unit_p4,
    )
    ctx_student = resolve_academic_context(user_b, institution_id=institution_a.id)
    assert ctx_student.has_academic_context is True
    assert ctx_student.academic_unit_ids == frozenset([unit_p4.id])

    # 2. Teacher assigned to P4 and P5
    teacher_mem = Membership.objects.create(
        user=user_a,
        institution=institution_a,
        role=MembershipRole.TEACHER,
        status=MembershipStatus.ACTIVE,
    )
    TeachingAssignment.objects.create(
        institution=institution_a,
        membership=teacher_mem,
        academic_unit=unit_p4,
        subject="Mathematics",
        status=TeachingAssignmentStatus.ACTIVE,
    )
    TeachingAssignment.objects.create(
        institution=institution_a,
        membership=teacher_mem,
        academic_unit=unit_p5,
        subject="Science",
        status=TeachingAssignmentStatus.ACTIVE,
    )
    ctx_teacher = resolve_academic_context(user_a, institution_id=institution_a.id)
    assert ctx_teacher.academic_unit_ids == frozenset([unit_p4.id, unit_p5.id])


@pytest.mark.django_db
def test_filter_libraries_prioritizes_utility_and_matching_units(
    institution_a, user_b
) -> None:
    """Universal utility libraries and matching academic units are retained; non-matching are filtered."""
    unit_p4 = AcademicUnit.objects.create(
        institution=institution_a, name="Primary 4", code="P4", order=4
    )
    unit_s6 = AcademicUnit.objects.create(
        institution=institution_a, name="Senior 6", code="S6", order=13
    )

    # Library 1: Universal Utility (School Handbook / Dictionary)
    lib_utility = Library.objects.create(
        institution=institution_a,
        name="School Utility Shelf",
        slug="school-utility",
        target_type=LibraryTargetType.UTILITY,
    )

    # Library 2: Targeted to P4
    lib_p4 = Library.objects.create(
        institution=institution_a,
        name="P4 Core Shelf",
        slug="p4-core",
        target_type=LibraryTargetType.ACADEMIC_UNIT,
        academic_unit=unit_p4,
    )

    # Library 3: Targeted to S6
    lib_s6 = Library.objects.create(
        institution=institution_a,
        name="S6 Advanced Shelf",
        slug="s6-advanced",
        target_type=LibraryTargetType.ACADEMIC_UNIT,
        academic_unit=unit_s6,
    )

    # Place student in P4
    Membership.objects.create(
        user=user_b,
        institution=institution_a,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.ACTIVE,
        academic_unit=unit_p4,
    )
    student_ctx = resolve_academic_context(user_b, institution_id=institution_a.id)

    # All three libraries authorized
    authorized_ids = frozenset([lib_utility.id, lib_p4.id, lib_s6.id])

    filtered_ids = filter_libraries_by_academic_context(authorized_ids, student_ctx)

    # Must retain utility and P4, but exclude S6
    assert lib_utility.id in filtered_ids
    assert lib_p4.id in filtered_ids
    assert lib_s6.id not in filtered_ids


@pytest.mark.django_db
def test_academic_relevance_never_bypasses_authorization(
    institution_a, user_b
) -> None:
    """CRITICAL INVARIANT: Academic unit match without authorization grant yields EMPTY scope."""
    unit_p4 = AcademicUnit.objects.create(
        institution=institution_a, name="Primary 4", code="P4", order=4
    )

    # Library targeted to P4, but user_b has NO LibraryAccessPolicy
    lib_p4 = Library.objects.create(
        institution=institution_a,
        name="Restricted P4 Exams",
        slug="p4-exams",
        target_type=LibraryTargetType.ACADEMIC_UNIT,
        academic_unit=unit_p4,
        visibility=LibraryVisibility.RESTRICTED,
    )

    Membership.objects.create(
        user=user_b,
        institution=institution_a,
        role=MembershipRole.STUDENT,
        status=MembershipStatus.ACTIVE,
        academic_unit=unit_p4,
    )

    # Resolve authoritative scope via policy
    policy = KnowledgeAuthorizationPolicy()
    scope = policy.resolve(user=user_b, requested_library_ids=[lib_p4.id])

    # Must be empty because academic relevance != authorization
    assert scope.is_empty is True
    assert lib_p4.id not in scope.authorized_library_ids
