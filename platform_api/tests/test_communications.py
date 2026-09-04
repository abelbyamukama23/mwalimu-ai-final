"""Tests for the Communications App (Notifications & Outbox)."""

from unittest.mock import patch
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from platform_api.apps.communications.intents import (
    CommunicationCategory,
    CommunicationChannel,
    CommunicationIntent,
)
from platform_api.apps.communications.models import (
    Notification,
    OutboxMessage,
    OutboxMessageStatus,
)
from platform_api.apps.communications.services import dispatch_intent
from platform_api.apps.communications.tasks import deliver_outbox_message
from platform_api.apps.users.models import User


@pytest.mark.django_db
class TestNotificationCenter:
    """Test suite for generic in-platform Notification Center."""

    def test_notification_user_isolation(self):
        """Users can only retrieve notifications addressed to them."""
        user_a = User.objects.create_user(email="user_a@test.com", password="password123")
        user_b = User.objects.create_user(email="user_b@test.com", password="password123")

        Notification.objects.create(
            recipient=user_a,
            notification_type="library.invitation",
            title="Invite to Physics",
            message="You were invited",
        )
        Notification.objects.create(
            recipient=user_b,
            notification_type="system.announcement",
            title="System Maintenance",
            message="Downtime scheduled",
        )

        client = APIClient()
        client.force_authenticate(user=user_a)

        res = client.get("/api/v1/notifications/")
        assert res.status_code == status.HTTP_200_OK
        results = res.data.get("results", res.data)
        assert len(results) == 1
        assert results[0]["title"] == "Invite to Physics"
        assert res.data.get("unread_count") == 1
        assert res["X-Unread-Count"] == "1"

    def test_filter_unread_notifications(self):
        """Filtering by ?unread=true returns only unread notifications."""
        user = User.objects.create_user(email="user@test.com", password="password123")
        n1 = Notification.objects.create(
            recipient=user,
            notification_type="membership.approved",
            title="Approved",
            message="Welcome",
            is_read=False,
        )
        Notification.objects.create(
            recipient=user,
            notification_type="system.announcement",
            title="Old Announcement",
            message="Old",
            is_read=True,
        )

        client = APIClient()
        client.force_authenticate(user=user)

        res = client.get("/api/v1/notifications/?unread=true")
        assert res.status_code == status.HTTP_200_OK
        results = res.data.get("results", res.data)
        assert len(results) == 1
        assert results[0]["id"] == str(n1.id)

    def test_mark_single_notification_read(self):
        """POST /api/v1/notifications/{id}/read/ marks notification as read."""
        user = User.objects.create_user(email="user@test.com", password="password123")
        n = Notification.objects.create(
            recipient=user,
            notification_type="library.invitation",
            title="Invite",
            message="Check it",
            is_read=False,
        )

        client = APIClient()
        client.force_authenticate(user=user)

        res = client.post(f"/api/v1/notifications/{n.id}/read/")
        assert res.status_code == status.HTTP_200_OK
        n.refresh_from_db()
        assert n.is_read is True
        assert n.read_at is not None
        assert res.data["unread_count"] == 0

    def test_cannot_mark_other_user_notification_read(self):
        """User cannot mark another user's notification as read."""
        user_a = User.objects.create_user(email="user_a@test.com", password="password123")
        user_b = User.objects.create_user(email="user_b@test.com", password="password123")
        n_b = Notification.objects.create(
            recipient=user_b,
            notification_type="system.announcement",
            title="User B Alert",
            message="Private",
        )

        client = APIClient()
        client.force_authenticate(user=user_a)

        res = client.post(f"/api/v1/notifications/{n_b.id}/read/")
        assert res.status_code == status.HTTP_404_NOT_FOUND
        n_b.refresh_from_db()
        assert n_b.is_read is False

    def test_mark_all_read(self):
        """POST /api/v1/notifications/read-all/ marks all unread for user."""
        user = User.objects.create_user(email="user@test.com", password="password123")
        Notification.objects.create(recipient=user, notification_type="n1", title="1", message="1")
        Notification.objects.create(recipient=user, notification_type="n2", title="2", message="2")

        client = APIClient()
        client.force_authenticate(user=user)

        res = client.post("/api/v1/notifications/read-all/")
        assert res.status_code == status.HTTP_200_OK
        assert res.data["updated_count"] == 2
        assert res.data["unread_count"] == 0

        assert Notification.objects.filter(recipient=user, is_read=False).count() == 0

    def test_unread_count_endpoint(self):
        """GET /api/v1/notifications/unread-count/ returns accurate integer."""
        user = User.objects.create_user(email="user@test.com", password="password123")
        Notification.objects.create(recipient=user, notification_type="n1", title="1", message="1")
        Notification.objects.create(recipient=user, notification_type="n2", title="2", message="2")
        Notification.objects.create(recipient=user, notification_type="n3", title="3", message="3", is_read=True)

        client = APIClient()
        client.force_authenticate(user=user)

        res = client.get("/api/v1/notifications/unread-count/")
        assert res.status_code == status.HTTP_200_OK
        assert res.data["unread_count"] == 2


@pytest.mark.django_db
class TestCommunicationIntentAndOutbox:
    """Test suite for intent classification and transactional outbox email delivery."""

    def test_dispatch_intent_creates_notification_and_outbox(self):
        """Dispatching an intent with both channels creates Notification and OutboxMessage."""
        inviter = User.objects.create_user(email="librarian@school.edu", password="password123")
        recipient = User.objects.create_user(email="student@school.edu", password="password123")

        context = {
            "inviter_email": inviter.email,
            "library_name": "Chemistry Shelf",
            "institution_name": "Makerere",
            "role": "student",
            "token": "test-token-123",
        }

        res = dispatch_intent(
            intent=CommunicationIntent.LIBRARY_INVITATION_EXISTING_USER,
            context=context,
            recipient_user=recipient,
            actor=inviter,
        )

        assert res["notification"] is not None
        assert res["outbox"] is not None

        # Verify in-platform notification created
        notif = Notification.objects.get(pk=res["notification"])
        assert notif.recipient == recipient
        assert notif.actor == inviter
        assert "Chemistry Shelf" in notif.title

        # Verify outbox message created
        outbox = OutboxMessage.objects.get(pk=res["outbox"])
        assert outbox.recipient_email == recipient.email
        assert outbox.category == CommunicationCategory.LIBRARY
        assert outbox.status == OutboxMessageStatus.PENDING
        assert "Chemistry Shelf" in outbox.subject

    def test_outbox_celery_delivery_success(self):
        """Celery delivery task updates status to SENT."""
        outbox = OutboxMessage.objects.create(
            intent=CommunicationIntent.AUTH_EMAIL_VERIFICATION,
            category=CommunicationCategory.AUTHENTICATION,
            recipient_email="test@user.com",
            subject="Verify your Account",
            html_body="<h1>123456</h1>",
            text_body="123456",
        )

        with patch(
            "platform_api.apps.communications.tasks._send_via_resend",
            return_value={"id": "resend_123"},
        ) as mock_send:
            deliver_outbox_message(str(outbox.id))
            mock_send.assert_called_once()

        outbox.refresh_from_db()
        assert outbox.status == OutboxMessageStatus.SENT
        assert outbox.external_reference == "resend_123"
        assert outbox.sent_at is not None
        assert outbox.attempts == 1

    def test_outbox_celery_delivery_failure_retry(self):
        """Celery delivery records error on failure and transitions to RETRYING."""
        outbox = OutboxMessage.objects.create(
            intent=CommunicationIntent.AUTH_EMAIL_VERIFICATION,
            category=CommunicationCategory.AUTHENTICATION,
            recipient_email="test@user.com",
            subject="Verify your Account",
            html_body="<h1>123456</h1>",
            text_body="123456",
        )

        with patch(
            "platform_api.apps.communications.tasks._send_via_resend",
            side_effect=RuntimeError("SMTP connection timeout"),
        ), pytest.raises(Exception):
            deliver_outbox_message(str(outbox.id))

        outbox.refresh_from_db()
        assert outbox.status == OutboxMessageStatus.RETRYING
        assert outbox.attempts == 1
        assert "SMTP connection timeout" in outbox.error_message
