"""Authorization and permission helpers for Mwalimu context domain."""

from __future__ import annotations

import uuid
from typing import Any

from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView

from platform_api.apps.context.models import ContextResource, ContextScopeType
from platform_api.apps.memberships.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
)
from platform_api.apps.users.models import User


def is_platform_admin(user: User | Any) -> bool:
    """Return True if the user is a platform staff member or superuser."""
    if not isinstance(user, User) or not user.is_authenticated:
        return False
    return bool(user.is_staff or user.is_superuser)


def is_institution_admin(
    user: User | Any, institution_id: uuid.UUID | str | None
) -> bool:
    """Return True if user is an active administrator of the given institution."""
    if not isinstance(user, User) or not user.is_authenticated or not institution_id:
        return False
    if user.is_superuser:
        return True
    return Membership.objects.filter(
        user=user,
        institution_id=institution_id,
        role=MembershipRole.ADMINISTRATOR,
        status=MembershipStatus.ACTIVE,
    ).exists()


def is_active_institution_member(
    user: User | Any, institution_id: uuid.UUID | str | None
) -> bool:
    """Return True if user has any active membership in the given institution."""
    if not isinstance(user, User) or not user.is_authenticated or not institution_id:
        return False
    if user.is_superuser:
        return True
    return Membership.objects.filter(
        user=user,
        institution_id=institution_id,
        status=MembershipStatus.ACTIVE,
    ).exists()


def can_manage_context_resource(user: User | Any, resource: ContextResource) -> bool:
    """Return True if user has permission to update or delete the context resource."""
    if resource.scope_type == ContextScopeType.PLATFORM:
        return is_platform_admin(user)
    if resource.scope_type == ContextScopeType.INSTITUTION:
        return is_institution_admin(user, resource.institution_id)
    return False


def can_view_context_resource(user: User | Any, resource: ContextResource) -> bool:
    """Return True if user has permission to read the context resource."""
    if resource.scope_type == ContextScopeType.PLATFORM:
        return True
    if resource.scope_type == ContextScopeType.INSTITUTION:
        return is_active_institution_member(user, resource.institution_id)
    return False


class IsPlatformAdmin(permissions.BasePermission):
    """DRF permission allowing access only to platform administrators."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Check if request user is a platform admin."""
        return is_platform_admin(request.user)
