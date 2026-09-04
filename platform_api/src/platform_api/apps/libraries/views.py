"""Views for the libraries app."""

import secrets
import uuid
from datetime import timedelta
from typing import Any

from django.db import models
from django.db.models import QuerySet
from django.utils import timezone
from rest_framework import permissions, status, views, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from platform_api.apps.memberships.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
)
from platform_api.apps.users.models import User

from .authz import can_manage_library, is_institution_admin
from .models import (
    Library,
    LibraryAccessPolicy,
    LibraryScopeType,
    LibraryStatus,
    LibraryVisibility,
)
from .serializers import LibraryAccessPolicySerializer, LibrarySerializer


class LibraryViewSet(viewsets.ModelViewSet):  # type: ignore[type-arg]
    """View set for library management.

    Supports both personal libraries (owned by individual users) and
    institutional libraries (owned by institutions and managed by
    institution administrators).
    """

    serializer_class = LibrarySerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self) -> QuerySet[Library]:
        """Return libraries the user is authorized to view.

        Returns personal libraries owned by the user, plus institutional
        libraries authorized through administrator memberships, discoverability,
        or explicit access policies.
        """
        user = self.request.user
        if not isinstance(user, User):
            return Library.objects.none()

        granted_library_ids = LibraryAccessPolicy.objects.filter(
            user=user,
        ).values_list("library_id", flat=True)

        institution_param = (
            self.request.query_params.get("institution_id")
            or self.request.headers.get("X-Institution-Id")
        )
        if institution_param:
            try:
                target_inst_id = uuid.UUID(str(institution_param))
            except (ValueError, TypeError):
                return Library.objects.none()

            is_admin = Membership.objects.filter(
                user=user,
                institution_id=target_inst_id,
                role=MembershipRole.ADMINISTRATOR,
                status=MembershipStatus.ACTIVE,
            ).exists()

            if is_admin:
                return Library.objects.filter(
                    institution_id=target_inst_id,
                    scope_type=LibraryScopeType.INSTITUTION,
                    status=LibraryStatus.ACTIVE,
                ).order_by("-created_at")

            is_member = Membership.objects.filter(
                user=user,
                institution_id=target_inst_id,
                status=MembershipStatus.ACTIVE,
            ).exists()

            if is_member:
                return (
                    Library.objects.filter(
                        institution_id=target_inst_id,
                        scope_type=LibraryScopeType.INSTITUTION,
                        status=LibraryStatus.ACTIVE,
                    )
                    .filter(
                        models.Q(visibility=LibraryVisibility.DISCOVERABLE)
                        | models.Q(id__in=granted_library_ids)
                    )
                    .order_by("-created_at")
                )

            return Library.objects.none()

        personal_q = models.Q(
            scope_type=LibraryScopeType.PERSONAL,
            owner=user,
        )

        admin_institution_ids = Membership.objects.filter(
            user=user,
            role=MembershipRole.ADMINISTRATOR,
            status=MembershipStatus.ACTIVE,
        ).values_list("institution_id", flat=True)

        member_institution_ids = Membership.objects.filter(
            user=user,
            status=MembershipStatus.ACTIVE,
        ).values_list("institution_id", flat=True)

        institutional_q = models.Q(
            scope_type=LibraryScopeType.INSTITUTION,
        ) & (
            models.Q(institution_id__in=admin_institution_ids)
            | models.Q(
                institution_id__in=member_institution_ids,
                visibility=LibraryVisibility.DISCOVERABLE,
            )
            | models.Q(id__in=granted_library_ids)
        )

        return (
            Library.objects.filter(status=LibraryStatus.ACTIVE)
            .filter(personal_q | institutional_q)
            .order_by("-created_at")
        )

    def perform_create(self, serializer: BaseSerializer[Any]) -> None:
        """Create a personal or institutional library.

        When institution_id is provided, validates that the user is an active
        administrator of the institution. When institution_id is omitted,
        creates a personal library owned by request.user.
        """
        institution_id = serializer.validated_data.get("institution_id")
        if institution_id:
            if not is_institution_admin(self.request.user, institution_id):
                raise PermissionDenied(
                    "You do not have permission to create a library in "
                    "this institution.",
                )
            library = serializer.save(
                scope_type=LibraryScopeType.INSTITUTION,
                institution_id=institution_id,
                owner=None,
            )
            from platform_api.apps.institutions.audit import record_audit_event
            from platform_api.apps.institutions.models import AuditAction

            record_audit_event(
                institution=library.institution,
                action=AuditAction.LIBRARY_CREATED,
                target_type="library",
                target_id=library.id,
                target_repr=library.name,
                actor=self.request.user,
                metadata={"visibility": library.visibility, "slug": library.slug},
                request=self.request,
            )
        else:
            serializer.save(
                scope_type=LibraryScopeType.PERSONAL,
                owner=self.request.user,
                institution=None,
            )

    def update(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Only library managers may update a library."""
        library = self.get_object()
        if not can_manage_library(request.user, library):
            raise PermissionDenied(
                "You do not have permission to update this library.",
            )
        response = super().update(request, *args, **kwargs)
        if library.institution:
            from platform_api.apps.institutions.audit import record_audit_event
            from platform_api.apps.institutions.models import AuditAction

            record_audit_event(
                institution=library.institution,
                action=AuditAction.LIBRARY_UPDATED,
                target_type="library",
                target_id=library.id,
                target_repr=library.name,
                actor=request.user,
                metadata={"updated_fields": list(request.data.keys())},
                request=request,
            )
        return response

    def partial_update(
        self, request: Request, *args: object, **kwargs: object
    ) -> Response:
        """Only library managers may partially update a library."""
        library = self.get_object()
        if not can_manage_library(request.user, library):
            raise PermissionDenied(
                "You do not have permission to update this library.",
            )
        response = super().partial_update(request, *args, **kwargs)
        if library.institution:
            from platform_api.apps.institutions.audit import record_audit_event
            from platform_api.apps.institutions.models import AuditAction

            record_audit_event(
                institution=library.institution,
                action=AuditAction.LIBRARY_UPDATED,
                target_type="library",
                target_id=library.id,
                target_repr=library.name,
                actor=request.user,
                metadata={"updated_fields": list(request.data.keys())},
                request=request,
            )
        return response

    def destroy(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Only library managers may delete a library."""
        library = self.get_object()
        if not can_manage_library(request.user, library):
            raise PermissionDenied(
                "You do not have permission to delete this library.",
            )
        inst = library.institution
        lib_id = library.id
        lib_name = library.name
        response = super().destroy(request, *args, **kwargs)
        if inst:
            from platform_api.apps.institutions.audit import record_audit_event
            from platform_api.apps.institutions.models import AuditAction

            record_audit_event(
                institution=inst,
                action=AuditAction.LIBRARY_DELETED,
                target_type="library",
                target_id=lib_id,
                target_repr=lib_name,
                actor=request.user,
                metadata={"deleted_library": lib_name},
                request=request,
            )
        return response


class LibraryAccessPolicyViewSet(viewsets.ModelViewSet):  # type: ignore[type-arg]
    """View set for managing library access policies.

    Only institution administrators and library administrators may view,
    create, update, or delete access policies for a library.
    """

    serializer_class = LibraryAccessPolicySerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "pk"

    def get_library(self) -> Library:
        """Return the library from the URL path parameter."""
        raw_library_id = self.kwargs.get("library_pk")
        library_id = uuid.UUID(str(raw_library_id))
        try:
            library = Library.objects.get(pk=library_id)
        except Library.DoesNotExist as exc:
            raise PermissionDenied("Library not found.") from exc

        if not can_manage_library(self.request.user, library):
            message = (
                "You do not have permission to manage access policies for this library."
            )
            raise PermissionDenied(message)
        return library

    def get_queryset(self) -> QuerySet[LibraryAccessPolicy]:
        """Return access policies for the library the user may manage."""
        library = self.get_library()
        return LibraryAccessPolicy.objects.filter(library=library).order_by(
            "-created_at"
        )

    def get_serializer_context(self) -> dict[str, Any]:
        """Include the library in serializer context."""
        context = super().get_serializer_context()
        context["library"] = self.get_library()
        return context

    def perform_create(self, serializer: BaseSerializer[Any]) -> None:
        """Create the policy scoped to the managed library."""
        library = self.get_library()
        policy = serializer.save(library=library)
        if library.institution:
            from platform_api.apps.institutions.audit import record_audit_event
            from platform_api.apps.institutions.models import AuditAction

            record_audit_event(
                institution=library.institution,
                action=AuditAction.ACCESS_GRANTED,
                target_type="access_policy",
                target_id=policy.id,
                target_repr=f"{policy.user.email} -> {library.name}",
                actor=self.request.user,
                metadata={"role": policy.role, "user_email": policy.user.email},
                request=self.request,
            )

    def perform_update(self, serializer: BaseSerializer[Any]) -> None:
        """Update the policy."""
        policy = serializer.save()
        library = policy.library
        if library.institution:
            from platform_api.apps.institutions.audit import record_audit_event
            from platform_api.apps.institutions.models import AuditAction

            record_audit_event(
                institution=library.institution,
                action=AuditAction.ACCESS_UPDATED,
                target_type="access_policy",
                target_id=policy.id,
                target_repr=f"{policy.user.email} -> {library.name}",
                actor=self.request.user,
                metadata={"role": policy.role, "user_email": policy.user.email},
                request=self.request,
            )

    def perform_destroy(self, instance: Any) -> None:
        """Revoke the policy."""
        library = instance.library
        inst = library.institution
        policy_id = instance.id
        user_email = instance.user.email
        super().perform_destroy(instance)
        if inst:
            from platform_api.apps.institutions.audit import record_audit_event
            from platform_api.apps.institutions.models import AuditAction

            record_audit_event(
                institution=inst,
                action=AuditAction.ACCESS_REVOKED,
                target_type="access_policy",
                target_id=policy_id,
                target_repr=f"{user_email} -> {library.name}",
                actor=self.request.user,
                metadata={"revoked_user": user_email},
                request=self.request,
            )


class LibraryInvitationViewSet(viewsets.ModelViewSet):  # type: ignore[type-arg]
    """View set for managing library invitations.

    Only authorized library managers and institution administrators may create,
    view, or revoke invitations for a library.
    """

    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "pk"

    def get_library(self) -> Library:
        """Return the library scoped from URL parameter with management check."""
        raw_library_id = self.kwargs.get("library_pk")
        library_id = uuid.UUID(str(raw_library_id))
        try:
            library = Library.objects.get(pk=library_id)
        except Library.DoesNotExist as exc:
            raise PermissionDenied("Library not found.") from exc

        if not can_manage_library(self.request.user, library):
            raise PermissionDenied(
                "You do not have permission to manage invitations for this library."
            )
        return library

    def get_serializer_class(self) -> Any:
        """Return input or full serializer depending on action."""
        from .serializers import (
            LibraryInvitationCreateSerializer,
            LibraryInvitationSerializer,
        )

        if self.action == "create":
            return LibraryInvitationCreateSerializer
        return LibraryInvitationSerializer

    def get_queryset(self) -> QuerySet[Any]:
        """Return invitations for the scoped library."""
        from .models import LibraryInvitation

        library = self.get_library()
        qs = LibraryInvitation.objects.filter(library=library).select_related(
            "library", "institution", "inviter", "inviter__profile"
        ).order_by("-created_at")

        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Invite a user by email to join the library."""
        import secrets
        from datetime import timedelta
        from rest_framework.exceptions import ValidationError as DRFValidationError
        from platform_api.apps.communications.intents import CommunicationIntent
        from platform_api.apps.communications.services import dispatch_intent
        from platform_api.apps.institutions.audit import record_audit_event
        from platform_api.apps.institutions.models import AuditAction
        from .models import LibraryInvitation, LibraryInvitationStatus
        from .serializers import (
            LibraryInvitationCreateSerializer,
            LibraryInvitationSerializer,
        )

        library = self.get_library()
        serializer = LibraryInvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].strip().lower()
        intended_access = serializer.validated_data["access"]

        # 1. Determine if email belongs to an existing user
        recipient_user = User.objects.filter(email__iexact=email).first()

        # 2. Check if user already has an active access policy
        if recipient_user and LibraryAccessPolicy.objects.filter(
            library=library, user=recipient_user
        ).exists():
            raise DRFValidationError(
                {"email": "This user already has an access policy for this library."}
            )

        # 3. Check if a pending invitation already exists for this library and email
        existing_pending = LibraryInvitation.objects.filter(
            library=library,
            recipient_email__iexact=email,
            status=LibraryInvitationStatus.PENDING,
        ).first()

        if existing_pending:
            if not existing_pending.is_expired:
                raise DRFValidationError(
                    {"email": "A pending invitation already exists for this email address."}
                )
            # Expired: mark it expired so a new invitation can be issued
            existing_pending.status = LibraryInvitationStatus.EXPIRED
            existing_pending.save(update_fields=["status", "updated_at"])

        # 4. Generate token and 7-day expiration
        token = secrets.token_urlsafe(32)
        expires_at = timezone.now() + timedelta(days=7)

        invitation = LibraryInvitation.objects.create(
            library=library,
            institution=library.institution,
            inviter=request.user,
            recipient_email=email,
            recipient_user=recipient_user,
            intended_access=intended_access,
            status=LibraryInvitationStatus.PENDING,
            token=token,
            expires_at=expires_at,
        )

        # 5. Record audit event (INVITATION_CREATED, not ACCESS_GRANTED)
        if library.institution:
            record_audit_event(
                institution=library.institution,
                action=AuditAction.INVITATION_CREATED,
                target_type="library_invitation",
                target_id=invitation.id,
                target_repr=f"Invite {email} -> {library.name} ({intended_access})",
                actor=request.user,
                metadata={
                    "recipient_email": email,
                    "role": intended_access,
                    "library_id": str(library.id),
                    "is_existing_user": bool(recipient_user),
                },
                request=request,
            )

        # 6. Dispatch communication intent
        inviter_email = getattr(request.user, "email", "A librarian")
        institution_name = library.institution.name if library.institution else "Mwalimu"

        context = {
            "inviter_email": inviter_email,
            "library_id": str(library.id),
            "library_name": library.name,
            "institution_name": institution_name,
            "role": intended_access,
            "token": token,
            "title": f"Invitation to {library.name}",
            "message": f"{inviter_email} invited you to join '{library.name}' as a {intended_access}.",
            "payload": {
                "invitation_id": str(invitation.id),
                "library_id": str(library.id),
                "library_name": library.name,
                "role": intended_access,
                "token": token,
            },
        }

        if recipient_user:
            dispatch_intent(
                intent=CommunicationIntent.LIBRARY_INVITATION_EXISTING_USER,
                context=context,
                recipient_user=recipient_user,
                actor=request.user,
                expires_at=expires_at,
            )
        else:
            dispatch_intent(
                intent=CommunicationIntent.LIBRARY_INVITATION_NEW_USER,
                context=context,
                recipient_email=email,
                actor=request.user,
                expires_at=expires_at,
            )

        output_serializer = LibraryInvitationSerializer(invitation)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="revoke")
    def revoke(self, request: Request, library_pk: str | None = None, pk: str | None = None) -> Response:
        """Revoke a pending library invitation."""
        from rest_framework.exceptions import ValidationError as DRFValidationError
        from platform_api.apps.communications.intents import CommunicationIntent
        from platform_api.apps.communications.services import dispatch_intent
        from platform_api.apps.institutions.audit import record_audit_event
        from platform_api.apps.institutions.models import AuditAction
        from .models import LibraryInvitationStatus
        from .serializers import LibraryInvitationSerializer

        invitation = self.get_object()
        if invitation.status != LibraryInvitationStatus.PENDING:
            raise DRFValidationError(
                {"detail": f"Cannot revoke invitation with status '{invitation.status}'."}
            )

        invitation.status = LibraryInvitationStatus.REVOKED
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["status", "revoked_at", "updated_at"])

        if invitation.library.institution:
            record_audit_event(
                institution=invitation.library.institution,
                action=AuditAction.INVITATION_REVOKED,
                target_type="library_invitation",
                target_id=invitation.id,
                target_repr=f"Revoked invite for {invitation.recipient_email} ({invitation.library.name})",
                actor=request.user,
                metadata={"recipient_email": invitation.recipient_email},
                request=request,
            )

        if invitation.recipient_user:
            dispatch_intent(
                intent=CommunicationIntent.LIBRARY_INVITATION_REVOKED,
                context={
                    "title": "Invitation Revoked",
                    "message": f"The invitation to join '{invitation.library.name}' was revoked by {request.user.email}.",
                    "payload": {"library_id": str(invitation.library.id)},
                },
                recipient_user=invitation.recipient_user,
                actor=request.user,
            )

        serializer = LibraryInvitationSerializer(invitation)
        return Response(serializer.data, status=status.HTTP_200_OK)


class PublicInvitationResolutionView(views.APIView):  # type: ignore[name-defined]
    """Public endpoint to resolve invitation details by secure token without email enumeration."""

    permission_classes = [permissions.AllowAny]

    def get(self, request: Request, token: str) -> Response:
        """Resolve invitation metadata by token."""
        from django.http import Http404
        from .models import LibraryInvitation
        from .serializers import PublicLibraryInvitationResolutionSerializer

        invitation = (
            LibraryInvitation.objects.filter(token=token)
            .select_related("library", "institution", "inviter", "inviter__profile")
            .first()
        )
        if not invitation:
            raise Http404("Invitation not found or invalid token.")

        serializer = PublicLibraryInvitationResolutionSerializer(invitation)
        return Response(serializer.data, status=status.HTTP_200_OK)


class InvitationAcceptView(views.APIView):  # type: ignore[name-defined]
    """Authoritative endpoint to accept a library invitation.

    Enforces email binding, active verified account, and transactional
    creation of the LibraryAccessPolicy and institution membership.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, token: str | None = None, pk: str | None = None) -> Response:
        """Accept the invitation and activate library access policy."""
        from django.db import transaction
        from rest_framework.exceptions import ValidationError as DRFValidationError
        from platform_api.apps.communications.intents import CommunicationIntent
        from platform_api.apps.communications.services import dispatch_intent
        from platform_api.apps.institutions.audit import record_audit_event
        from platform_api.apps.institutions.models import AuditAction
        from .models import LibraryInvitation, LibraryInvitationStatus

        # 1. Require verified account
        if not getattr(request.user, "is_email_verified", False):
            raise PermissionDenied(
                "You must verify your email address before accepting library invitations."
            )

        with transaction.atomic():
            query = LibraryInvitation.objects.select_for_update()
            if token:
                invitation = query.filter(token=token).first()
            elif pk:
                invitation = query.filter(pk=pk).first()
            else:
                invitation = None

            if not invitation:
                raise PermissionDenied("Invitation not found or invalid.")

            # 2. Check lifecycle status
            if invitation.status != LibraryInvitationStatus.PENDING:
                raise DRFValidationError(
                    {"detail": f"This invitation has already been {invitation.status}."}
                )

            # 3. Check expiration
            if invitation.is_expired:
                invitation.status = LibraryInvitationStatus.EXPIRED
                invitation.save(update_fields=["status", "updated_at"])
                raise DRFValidationError(
                    {"detail": "This invitation has expired. Please ask the librarian for a new invite."}
                )

            # 4. Strict email binding invariant
            user_email = request.user.email.strip().lower()
            target_email = invitation.recipient_email.strip().lower()
            if user_email != target_email:
                raise PermissionDenied(
                    f"This invitation was sent to {target_email}. You are currently signed in as {user_email}."
                )

            # 5. Update invitation status atomically
            now = timezone.now()
            invitation.status = LibraryInvitationStatus.ACCEPTED
            invitation.accepted_at = now
            invitation.recipient_user = request.user
            invitation.save(update_fields=["status", "accepted_at", "recipient_user", "updated_at"])

            # 6. Ensure institution membership exists if institutional library
            if invitation.institution:
                Membership.objects.get_or_create(
                    user=request.user,
                    institution=invitation.institution,
                    defaults={
                        "role": MembershipRole.STUDENT,
                        "status": MembershipStatus.ACTIVE,
                    },
                )

            # 7. Create or update LibraryAccessPolicy (reusing existing auth model)
            policy, created = LibraryAccessPolicy.objects.update_or_create(
                library=invitation.library,
                user=request.user,
                defaults={"role": invitation.intended_access},
            )

            # 8. Record audit events
            if invitation.library.institution:
                record_audit_event(
                    institution=invitation.library.institution,
                    action=AuditAction.INVITATION_ACCEPTED,
                    target_type="library_invitation",
                    target_id=invitation.id,
                    target_repr=f"Accepted invite for {user_email} ({invitation.library.name})",
                    actor=request.user,
                    metadata={"role": invitation.intended_access},
                    request=request,
                )
                record_audit_event(
                    institution=invitation.library.institution,
                    action=AuditAction.ACCESS_GRANTED,
                    target_type="access_policy",
                    target_id=policy.id,
                    target_repr=f"{user_email} -> {invitation.library.name}",
                    actor=request.user,
                    metadata={"role": policy.role, "via": "invitation_accepted"},
                    request=request,
                )

            # 9. Notify inviter
            dispatch_intent(
                intent=CommunicationIntent.LIBRARY_INVITATION_ACCEPTED,
                context={
                    "recipient_email": user_email,
                    "library_name": invitation.library.name,
                    "role": invitation.intended_access,
                    "title": f"Invitation Accepted: {invitation.library.name}",
                    "message": f"{user_email} accepted your invitation to join '{invitation.library.name}' as a {invitation.intended_access}.",
                    "payload": {
                        "library_id": str(invitation.library.id),
                        "user_id": str(request.user.id),
                    },
                },
                recipient_user=invitation.inviter,
                actor=request.user,
            )

            return Response(
                {
                    "status": "accepted",
                    "library_id": str(invitation.library.id),
                    "library_name": invitation.library.name,
                    "role": invitation.intended_access,
                    "message": f"Successfully joined {invitation.library.name}.",
                },
                status=status.HTTP_200_OK,
            )


class InvitationDeclineView(views.APIView):  # type: ignore[name-defined]
    """Authoritative endpoint to decline a library invitation."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, token: str | None = None, pk: str | None = None) -> Response:
        """Decline the invitation without granting access."""
        from django.db import transaction
        from rest_framework.exceptions import ValidationError as DRFValidationError
        from platform_api.apps.communications.intents import CommunicationIntent
        from platform_api.apps.communications.services import dispatch_intent
        from platform_api.apps.institutions.audit import record_audit_event
        from platform_api.apps.institutions.models import AuditAction
        from .models import LibraryInvitation, LibraryInvitationStatus

        with transaction.atomic():
            query = LibraryInvitation.objects.select_for_update()
            if token:
                invitation = query.filter(token=token).first()
            elif pk:
                invitation = query.filter(pk=pk).first()
            else:
                invitation = None

            if not invitation:
                raise PermissionDenied("Invitation not found or invalid.")

            if invitation.status != LibraryInvitationStatus.PENDING:
                raise DRFValidationError(
                    {"detail": f"This invitation has already been {invitation.status}."}
                )

            user_email = request.user.email.strip().lower()
            target_email = invitation.recipient_email.strip().lower()
            if user_email != target_email:
                raise PermissionDenied(
                    f"This invitation was sent to {target_email}. You are currently signed in as {user_email}."
                )

            invitation.status = LibraryInvitationStatus.DECLINED
            invitation.declined_at = timezone.now()
            invitation.save(update_fields=["status", "declined_at", "updated_at"])

            if invitation.library.institution:
                record_audit_event(
                    institution=invitation.library.institution,
                    action=AuditAction.INVITATION_DECLINED,
                    target_type="library_invitation",
                    target_id=invitation.id,
                    target_repr=f"Declined invite for {user_email} ({invitation.library.name})",
                    actor=request.user,
                    request=request,
                )

            dispatch_intent(
                intent=CommunicationIntent.LIBRARY_INVITATION_DECLINED,
                context={
                    "recipient_email": user_email,
                    "library_name": invitation.library.name,
                    "title": f"Invitation Declined: {invitation.library.name}",
                    "message": f"{user_email} declined the invitation to join '{invitation.library.name}'.",
                },
                recipient_user=invitation.inviter,
                actor=request.user,
            )

            return Response(
                {
                    "status": "declined",
                    "library_id": str(invitation.library.id),
                    "message": f"Declined invitation to {invitation.library.name}.",
                },
                status=status.HTTP_200_OK,
            )

