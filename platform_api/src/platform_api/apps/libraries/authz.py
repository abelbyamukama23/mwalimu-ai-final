"""Shared library authorization helpers.

These helpers encode the Slice 2 authorization model so it can be reused by
other apps (e.g., resources) without duplicating policy logic.
"""

from typing import Any

from platform_api.apps.memberships.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
)
from platform_api.apps.users.models import User

from .models import (
    Library,
    LibraryAccessPolicy,
    LibraryAccessRole,
    LibraryScopeType,
    LibraryVisibility,
)


def is_institution_admin(user: User | Any, institution_id: Any) -> bool:
    """Return True if the user is an active administrator of the institution."""
    if not isinstance(user, User) or not institution_id:
        return False
    return Membership.objects.filter(
        user=user,
        institution_id=institution_id,
        role=MembershipRole.ADMINISTRATOR,
        status=MembershipStatus.ACTIVE,
    ).exists()


def is_active_institution_member(user: User | Any, institution_id: Any) -> bool:
    """Return True if the user has any active membership in the institution."""
    if not isinstance(user, User) or not institution_id:
        return False
    return Membership.objects.filter(
        user=user,
        institution_id=institution_id,
        status=MembershipStatus.ACTIVE,
    ).exists()


def has_library_role(
    user: User | Any,
    library: Library,
    roles: tuple[LibraryAccessRole, ...] | None = None,
) -> bool:
    """Return True if the user has an explicit access policy for the library."""
    if not isinstance(user, User):
        return False
    queryset = LibraryAccessPolicy.objects.filter(user=user, library=library)
    if roles:
        queryset = queryset.filter(role__in=roles)
    return queryset.exists()


def can_access_library(user: User | Any, library: Library) -> bool:
    """Return True if the user may view the library.

    For personal libraries, access is granted strictly to the owner.
    For institutional libraries, access is granted to institution
    administrators, users with an explicit access policy, or active members of
    discoverable libraries.
    """
    if library.scope_type == LibraryScopeType.PERSONAL:
        return bool(user and getattr(user, "id", None) == library.owner_id)

    if is_institution_admin(user, library.institution_id):
        return True
    if has_library_role(user, library):
        return True
    if library.visibility == LibraryVisibility.DISCOVERABLE:
        return is_active_institution_member(user, library.institution_id)
    return False


def can_manage_library(user: User | Any, library: Library) -> bool:
    """Return True if the user may manage the library and its policies.

    For personal libraries, management is granted strictly to the owner.
    For institutional libraries, management is granted to institution
    administrators or library administrators with an explicit policy.
    """
    if library.scope_type == LibraryScopeType.PERSONAL:
        return bool(user and getattr(user, "id", None) == library.owner_id)

    if is_institution_admin(user, library.institution_id):
        return True
    return has_library_role(
        user,
        library,
        roles=(LibraryAccessRole.ADMINISTRATOR,),
    )
