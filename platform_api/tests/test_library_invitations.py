"""Tests for First-Class Library Invitation Domain & Security Invariants."""

from datetime import timedelta
import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from platform_api.apps.communications.models import Notification, OutboxMessage
from platform_api.apps.institutions.models import AuditAction, Institution, InstitutionalAuditEvent
from platform_api.apps.libraries.models import (
    Library,
    LibraryAccessPolicy,
    LibraryAccessRole,
    LibraryInvitation,
    LibraryInvitationStatus,
    LibraryScopeType,
)
from platform_api.apps.memberships.models import Membership, MembershipRole, MembershipStatus
from platform_api.apps.users.models import User


@pytest.fixture
def test_setup():
    """Setup an institution with an institutional library, librarian, and member."""
    institution = Institution.objects.create(name="Makerere University", slug="makerere")
    librarian = User.objects.create_user(
        email="librarian@makerere.edu",
        password="password123",
        is_email_verified=True,
    )
    Membership.objects.create(
        user=librarian,
        institution=institution,
        role=MembershipRole.ADMINISTRATOR,
        status=MembershipStatus.ACTIVE,
    )

    library = Library.objects.create(
        institution=institution,
        scope_type=LibraryScopeType.INSTITUTION,
        name="Engineering Shelf",
        slug="engineering",
    )

    return {
        "institution": institution,
        "librarian": librarian,
        "library": library,
    }


@pytest.mark.django_db
class TestLibraryInvitations:
    """Comprehensive test suite for Library Invitations."""

    def test_librarian_can_invite_existing_user(self, test_setup):
        """Librarian invites an existing user -> creates Notification + Outbox + Audit log."""
        data = test_setup
        existing_student = User.objects.create_user(
            email="student@makerere.edu",
            password="password123",
            is_email_verified=True,
        )

        client = APIClient()
        client.force_authenticate(user=data["librarian"])

        res = client.post(
            f"/api/v1/libraries/{data['library'].id}/invitations/",
            {"email": existing_student.email, "access": "student"},
            format="json",
        )
        assert res.status_code == status.HTTP_201_CREATED
        invite_id = res.data["id"]
        assert res.data["status"] == "pending"
        assert res.data["intended_access"] == "student"

        # Verify LibraryInvitation in DB
        invite = LibraryInvitation.objects.get(pk=invite_id)
        assert invite.recipient_user == existing_student
        assert invite.recipient_email == existing_student.email

        # Audit event recorded is INVITATION_CREATED, NOT ACCESS_GRANTED
        audit = InstitutionalAuditEvent.objects.filter(
            institution=data["institution"], action=AuditAction.INVITATION_CREATED
        ).first()
        assert audit is not None
        assert InstitutionalAuditEvent.objects.filter(
            institution=data["institution"], action=AuditAction.ACCESS_GRANTED
        ).count() == 0

        # In-platform notification created for recipient
        notif = Notification.objects.filter(recipient=existing_student).first()
        assert notif is not None
        assert "Engineering Shelf" in notif.title
        assert notif.payload["invitation_id"] == str(invite.id)

        # Outbox email created
        outbox = OutboxMessage.objects.filter(recipient_email=existing_student.email).first()
        assert outbox is not None

    def test_librarian_can_invite_unregistered_email(self, test_setup):
        """Librarian invites an unregistered email -> recipient_user is null, Outbox created."""
        data = test_setup
        new_email = "freshman@external.com"

        client = APIClient()
        client.force_authenticate(user=data["librarian"])

        res = client.post(
            f"/api/v1/libraries/{data['library'].id}/invitations/",
            {"email": new_email, "access": "teacher"},
            format="json",
        )
        assert res.status_code == status.HTTP_201_CREATED
        invite = LibraryInvitation.objects.get(pk=res.data["id"])
        assert invite.recipient_user is None
        assert invite.recipient_email == new_email
        assert invite.intended_access == "teacher"

        # Outbox email queued
        outbox = OutboxMessage.objects.filter(recipient_email=new_email).first()
        assert outbox is not None
        assert invite.token in outbox.html_body

    def test_unauthorized_member_cannot_create_invitation(self, test_setup):
        """Standard student with no library admin rights cannot create invitations."""
        data = test_setup
        student = User.objects.create_user(email="random@student.edu", password="password123")
        Membership.objects.create(
            user=student,
            institution=data["institution"],
            role=MembershipRole.STUDENT,
            status=MembershipStatus.ACTIVE,
        )

        client = APIClient()
        client.force_authenticate(user=student)

        res = client.post(
            f"/api/v1/libraries/{data['library'].id}/invitations/",
            {"email": "someone@test.com", "access": "student"},
            format="json",
        )
        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_reject_duplicate_pending_invitation(self, test_setup):
        """Cannot create duplicate pending invitations to the same email for a library."""
        data = test_setup
        target_email = "duplicate@test.com"

        client = APIClient()
        client.force_authenticate(user=data["librarian"])

        res1 = client.post(
            f"/api/v1/libraries/{data['library'].id}/invitations/",
            {"email": target_email, "access": "student"},
            format="json",
        )
        assert res1.status_code == status.HTTP_201_CREATED

        res2 = client.post(
            f"/api/v1/libraries/{data['library'].id}/invitations/",
            {"email": target_email, "access": "student"},
            format="json",
        )
        assert res2.status_code == status.HTTP_400_BAD_REQUEST
        assert "A pending invitation already exists" in str(res2.data)

    def test_reject_invitation_to_existing_policy_holder(self, test_setup):
        """Cannot invite a user who already has an active access policy."""
        data = test_setup
        member = User.objects.create_user(email="already_member@test.com", password="password123")
        LibraryAccessPolicy.objects.create(
            library=data["library"],
            user=member,
            role=LibraryAccessRole.STUDENT,
        )

        client = APIClient()
        client.force_authenticate(user=data["librarian"])

        res = client.post(
            f"/api/v1/libraries/{data['library'].id}/invitations/",
            {"email": member.email, "access": "student"},
            format="json",
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "already has an access policy" in str(res.data)

    def test_public_token_resolution_anti_enumeration(self, test_setup):
        """Public token resolution masks email to prevent enumeration."""
        data = test_setup
        invite = LibraryInvitation.objects.create(
            library=data["library"],
            institution=data["institution"],
            inviter=data["librarian"],
            recipient_email="secret_student@domain.com",
            intended_access=LibraryAccessRole.STUDENT,
            status=LibraryInvitationStatus.PENDING,
            token="secure_token_xyz_999",
            expires_at=timezone.now() + timedelta(days=7),
        )

        client = APIClient()  # Unauthenticated
        res = client.get(f"/api/v1/invitations/{invite.token}/")
        assert res.status_code == status.HTTP_200_OK
        assert res.data["library_name"] == "Engineering Shelf"
        assert res.data["institution_name"] == "Makerere University"
        # Masked email: does not leak full email
        assert res.data["recipient_email_masked"] == "s***t@domain.com"
        assert "secret_student@domain.com" not in str(res.data)

    def test_accept_invitation_by_verified_matching_user(self, test_setup):
        """Accepting an invitation transactionally creates access policy and logs audit."""
        data = test_setup
        student = User.objects.create_user(
            email="alice@student.edu",
            password="password123",
            is_email_verified=True,
        )

        invite = LibraryInvitation.objects.create(
            library=data["library"],
            institution=data["institution"],
            inviter=data["librarian"],
            recipient_email="alice@student.edu",
            recipient_user=student,
            intended_access=LibraryAccessRole.STUDENT,
            status=LibraryInvitationStatus.PENDING,
            token="token_alice_123",
            expires_at=timezone.now() + timedelta(days=7),
        )

        client = APIClient()
        client.force_authenticate(user=student)

        res = client.post(f"/api/v1/invitations/{invite.token}/accept/")
        assert res.status_code == status.HTTP_200_OK
        assert res.data["status"] == "accepted"

        # Check invitation state
        invite.refresh_from_db()
        assert invite.status == LibraryInvitationStatus.ACCEPTED
        assert invite.accepted_at is not None

        # Check LibraryAccessPolicy created
        policy = LibraryAccessPolicy.objects.filter(
            library=data["library"], user=student
        ).first()
        assert policy is not None
        assert policy.role == LibraryAccessRole.STUDENT

        # Check institutional membership created
        mem = Membership.objects.filter(
            institution=data["institution"], user=student
        ).first()
        assert mem is not None
        assert mem.status == MembershipStatus.ACTIVE

        # Check audit event for ACCESS_GRANTED is now recorded
        assert InstitutionalAuditEvent.objects.filter(
            institution=data["institution"], action=AuditAction.ACCESS_GRANTED
        ).exists()

        # Check notification dispatched to inviter
        assert Notification.objects.filter(
            recipient=data["librarian"], notification_type="library.invitation.accepted"
        ).exists()

    def test_reject_acceptance_from_wrong_account(self, test_setup):
        """User B cannot accept an invitation intended for User A (email binding invariant)."""
        data = test_setup
        invite = LibraryInvitation.objects.create(
            library=data["library"],
            institution=data["institution"],
            inviter=data["librarian"],
            recipient_email="intended@victim.com",
            intended_access=LibraryAccessRole.STUDENT,
            status=LibraryInvitationStatus.PENDING,
            token="token_wrong_account",
            expires_at=timezone.now() + timedelta(days=7),
        )

        attacker = User.objects.create_user(
            email="attacker@evil.com",
            password="password123",
            is_email_verified=True,
        )

        client = APIClient()
        client.force_authenticate(user=attacker)

        res = client.post(f"/api/v1/invitations/{invite.token}/accept/")
        assert res.status_code == status.HTTP_403_FORBIDDEN
        assert "This invitation was sent to" in str(res.data)

        # Ensure no policy was granted
        assert not LibraryAccessPolicy.objects.filter(user=attacker).exists()

    def test_reject_acceptance_from_unverified_account(self, test_setup):
        """Unverified accounts must verify email before claiming library invitations."""
        data = test_setup
        unverified_user = User.objects.create_user(
            email="unverified@test.com",
            password="password123",
            is_email_verified=False,
        )

        invite = LibraryInvitation.objects.create(
            library=data["library"],
            institution=data["institution"],
            inviter=data["librarian"],
            recipient_email="unverified@test.com",
            recipient_user=unverified_user,
            intended_access=LibraryAccessRole.STUDENT,
            status=LibraryInvitationStatus.PENDING,
            token="token_unverified",
            expires_at=timezone.now() + timedelta(days=7),
        )

        client = APIClient()
        client.force_authenticate(user=unverified_user)

        res = client.post(f"/api/v1/invitations/{invite.token}/accept/")
        assert res.status_code == status.HTTP_403_FORBIDDEN
        assert "verify your email" in str(res.data)

    def test_reject_expired_invitation(self, test_setup):
        """Expired invitations cannot be accepted."""
        data = test_setup
        student = User.objects.create_user(
            email="student@expired.com",
            password="password123",
            is_email_verified=True,
        )

        invite = LibraryInvitation.objects.create(
            library=data["library"],
            institution=data["institution"],
            inviter=data["librarian"],
            recipient_email="student@expired.com",
            recipient_user=student,
            intended_access=LibraryAccessRole.STUDENT,
            status=LibraryInvitationStatus.PENDING,
            token="token_expired_1",
            expires_at=timezone.now() - timedelta(days=1),  # Expired yesterday
        )

        client = APIClient()
        client.force_authenticate(user=student)

        res = client.post(f"/api/v1/invitations/{invite.token}/accept/")
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "expired" in str(res.data)

    def test_token_replay_prevention(self, test_setup):
        """Already processed invitations cannot be accepted a second time."""
        data = test_setup
        student = User.objects.create_user(
            email="replay@test.com",
            password="password123",
            is_email_verified=True,
        )

        invite = LibraryInvitation.objects.create(
            library=data["library"],
            institution=data["institution"],
            inviter=data["librarian"],
            recipient_email="replay@test.com",
            recipient_user=student,
            intended_access=LibraryAccessRole.STUDENT,
            status=LibraryInvitationStatus.ACCEPTED,
            accepted_at=timezone.now(),
            token="token_replay",
            expires_at=timezone.now() + timedelta(days=7),
        )

        client = APIClient()
        client.force_authenticate(user=student)

        res = client.post(f"/api/v1/invitations/{invite.token}/accept/")
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "already been accepted" in str(res.data)

    def test_librarian_can_revoke_invitation(self, test_setup):
        """Librarian may revoke a pending invitation."""
        data = test_setup
        invite = LibraryInvitation.objects.create(
            library=data["library"],
            institution=data["institution"],
            inviter=data["librarian"],
            recipient_email="to_revoke@test.com",
            intended_access=LibraryAccessRole.STUDENT,
            status=LibraryInvitationStatus.PENDING,
            token="token_to_revoke",
            expires_at=timezone.now() + timedelta(days=7),
        )

        client = APIClient()
        client.force_authenticate(user=data["librarian"])

        res = client.post(
            f"/api/v1/libraries/{data['library'].id}/invitations/{invite.id}/revoke/"
        )
        assert res.status_code == status.HTTP_200_OK
        invite.refresh_from_db()
        assert invite.status == LibraryInvitationStatus.REVOKED
        assert invite.revoked_at is not None

        # Audit log recorded
        assert InstitutionalAuditEvent.objects.filter(
            institution=data["institution"], action=AuditAction.INVITATION_REVOKED
        ).exists()

    def test_recipient_can_decline_invitation(self, test_setup):
        """Recipient may decline invitation; no access policy is granted."""
        data = test_setup
        student = User.objects.create_user(
            email="declining@student.com",
            password="password123",
            is_email_verified=True,
        )

        invite = LibraryInvitation.objects.create(
            library=data["library"],
            institution=data["institution"],
            inviter=data["librarian"],
            recipient_email="declining@student.com",
            recipient_user=student,
            intended_access=LibraryAccessRole.STUDENT,
            status=LibraryInvitationStatus.PENDING,
            token="token_to_decline",
            expires_at=timezone.now() + timedelta(days=7),
        )

        client = APIClient()
        client.force_authenticate(user=student)

        res = client.post(f"/api/v1/invitations/{invite.token}/decline/")
        assert res.status_code == status.HTTP_200_OK
        invite.refresh_from_db()
        assert invite.status == LibraryInvitationStatus.DECLINED
        assert invite.declined_at is not None

        # Ensure no access policy was created
        assert not LibraryAccessPolicy.objects.filter(user=student).exists()

        # Check inviter was notified of decline
        assert Notification.objects.filter(
            recipient=data["librarian"], notification_type="library.invitation.declined"
        ).exists()
