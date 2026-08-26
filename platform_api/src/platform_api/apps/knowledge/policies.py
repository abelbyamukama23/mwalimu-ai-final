"""Domain authorization policies for knowledge retrieval."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from platform_api.apps.libraries.models import (
    Library,
    LibraryAccessPolicy,
    LibraryScopeType,
    LibraryStatus,
)
from platform_api.apps.memberships.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
)
from platform_api.apps.resources.models import Resource, ResourceStatus
from platform_api.apps.users.models import User


@dataclass(frozen=True)
class EffectiveRetrievalScope:
    """Immutable value object defining authorized retrieval boundaries."""

    authorized_library_ids: frozenset[uuid.UUID]
    authorized_resource_ids: frozenset[uuid.UUID] | None

    @property
    def is_empty(self) -> bool:
        """Return True if scope contains zero retrievable targets."""
        return len(self.authorized_library_ids) == 0 or (
            self.authorized_resource_ids is not None
            and len(self.authorized_resource_ids) == 0
        )


class KnowledgeAuthorizationPolicy:
    """Server-authoritative policy resolving effective knowledge retrieval scopes.

    Enforces:
    1. Discovery != Retrieval: Discoverable libraries do not grant knowledge
       retrieval without an explicit LibraryAccessPolicy or Institution Admin role.
    2. Strict Scope Narrowing:
       Effective Scope = Requested Scope ∩ Server-Authorized Scope.
    3. Resource Scoping: Resource filters are validated against authorized libraries.
    4. Fail Closed: Zero authorized libraries or empty intersection yields
       an empty scope.
    5. Knowledge Scope Semantics (carried authoritatively in the delegated token):
       - "my"          -> personal libraries owned by the user only.
       - "institution" -> authorized institutional libraries only.
       - "public"      -> no library retrieval (public/platform context only).
       - "relevant"/None -> all server-authorized libraries.
    """

    def resolve(
        self,
        user: User,
        requested_library_ids: Sequence[uuid.UUID] | None = None,
        requested_resource_ids: Sequence[uuid.UUID] | None = None,
        scope_type: str | None = None,
    ) -> EffectiveRetrievalScope:
        """Resolve the immutable effective retrieval scope for the user.

        Args:
            user: Authenticated user (execution identity).
            requested_library_ids: Optional caller-specified library filters.
            requested_resource_ids: Optional caller-specified resource filters.
            scope_type: Optional authoritative knowledge scope
                ("relevant" | "my" | "institution" | "public").

        Returns:
            Immutable EffectiveRetrievalScope instance.
        """
        if not getattr(user, "is_authenticated", False):
            return EffectiveRetrievalScope(frozenset(), frozenset())

        # 1. Resolve personal libraries owned by the user
        personal_library_ids = Library.objects.filter(
            owner=user,
            scope_type=LibraryScopeType.PERSONAL,
            status=LibraryStatus.ACTIVE,
        ).values_list("id", flat=True)

        # 2. Resolve active institution memberships where user is Administrator
        admin_institution_ids = Membership.objects.filter(
            user=user,
            role=MembershipRole.ADMINISTRATOR,
            status=MembershipStatus.ACTIVE,
        ).values_list("institution_id", flat=True)

        admin_library_ids = Library.objects.filter(
            institution_id__in=admin_institution_ids,
            scope_type=LibraryScopeType.INSTITUTION,
            status=LibraryStatus.ACTIVE,
        ).values_list("id", flat=True)

        # 3. Resolve libraries where user has an explicit active LibraryAccessPolicy
        policy_library_ids = LibraryAccessPolicy.objects.filter(
            user=user,
            library__status=LibraryStatus.ACTIVE,
        ).values_list("library_id", flat=True)

        server_authorized_library_ids = (
            set(personal_library_ids) | set(admin_library_ids) | set(policy_library_ids)
        )

        if not server_authorized_library_ids:
            return EffectiveRetrievalScope(frozenset(), frozenset())

        # 4. Intersect with requested_library_ids (narrowing)
        if requested_library_ids is not None:
            effective_library_ids = (
                set(requested_library_ids) & server_authorized_library_ids
            )
        else:
            effective_library_ids = server_authorized_library_ids

        # 5. Apply authoritative knowledge-scope semantics
        effective_library_ids = self._apply_scope_type(
            effective_library_ids, user, scope_type
        )

        if not effective_library_ids:
            return EffectiveRetrievalScope(frozenset(), frozenset())

        # 6. Resolve resource scoping if requested
        effective_resource_ids: set[uuid.UUID] | None = None
        if requested_resource_ids is not None:
            if len(requested_resource_ids) == 0:
                effective_resource_ids = set()
            else:
                valid_resources = Resource.objects.filter(
                    id__in=requested_resource_ids,
                    library_id__in=effective_library_ids,
                    status=ResourceStatus.READY,
                ).values_list("id", flat=True)
                effective_resource_ids = set(valid_resources)

        return EffectiveRetrievalScope(
            authorized_library_ids=frozenset(effective_library_ids),
            authorized_resource_ids=(
                frozenset(effective_resource_ids)
                if effective_resource_ids is not None
                else None
            ),
        )

    @staticmethod
    def _apply_scope_type(
        library_ids: set[uuid.UUID],
        user: User,
        scope_type: str | None,
    ) -> set[uuid.UUID]:
        """Narrow authorized library IDs to the selected knowledge scope."""
        normalized = (scope_type or "").strip().lower()
        if normalized in ("", "relevant"):
            return library_ids
        if normalized == "public":
            return set()

        qs = Library.objects.filter(id__in=library_ids, status=LibraryStatus.ACTIVE)
        if normalized == "my":
            return set(
                qs.filter(
                    scope_type=LibraryScopeType.PERSONAL, owner=user
                ).values_list("id", flat=True)
            )
        if normalized == "institution":
            return set(
                qs.filter(scope_type=LibraryScopeType.INSTITUTION).values_list(
                    "id", flat=True
                )
            )
        return library_ids
