"""Communication dispatch service for platform intents."""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.utils import timezone

from platform_api.apps.users.models import User

from .intents import (
    INTENT_REGISTRY,
    CommunicationCategory,
    CommunicationChannel,
    CommunicationIntent,
    IntentMetadata,
)
from .models import Notification, OutboxMessage, OutboxMessageStatus
from .tasks import deliver_outbox_message
from .templates import render_template_for_intent

logger = logging.getLogger(__name__)


def dispatch_intent(
    intent: CommunicationIntent,
    context: dict[str, Any],
    recipient_user: User | None = None,
    recipient_email: str | None = None,
    actor: User | None = None,
    idempotency_key: str | None = None,
    channels: list[CommunicationChannel] | tuple[CommunicationChannel, ...] | None = None,
    expires_at: timezone.datetime | None = None,
) -> dict[str, Any]:
    """Dispatch a platform communication intent across configured delivery channels.

    Guarantees isolation of domain transactions:
    - In-app notifications are stored immediately in the database.
    - Emails are queued in the transactional OutboxMessage table and dispatched
      asynchronously via Celery on transaction commit.
    """
    if recipient_user and not recipient_email:
        recipient_email = recipient_user.email

    meta = INTENT_REGISTRY.get(
        intent,
        IntentMetadata(
            category=CommunicationCategory.SYSTEM,
            default_channels=(CommunicationChannel.IN_APP_NOTIFICATION,),
        ),
    )

    effective_channels = channels or meta.default_channels
    results: dict[str, Any] = {
        "intent": intent,
        "notification": None,
        "outbox": None,
    }

    # 1. In-Platform Notification
    if CommunicationChannel.IN_APP_NOTIFICATION in effective_channels and recipient_user:
        notification_type = meta.notification_type or str(intent.value)
        title = context.get("title")
        message = context.get("message")

        # If title or message not explicitly supplied in context, synthesize from template
        if not title or not message:
            rendered = render_template_for_intent(intent, context)
            if not title:
                title = rendered.subject
            if not message:
                message = rendered.text_body or rendered.subject

        payload = context.get("payload") or {}

        notification = Notification.objects.create(
            recipient=recipient_user,
            actor=actor,
            notification_type=notification_type,
            title=title[:255],
            message=message,
            payload=payload,
            expires_at=expires_at,
        )
        results["notification"] = str(notification.id)
        logger.info(
            "Created in-platform notification %s (%s) for user %s",
            notification.id,
            notification_type,
            recipient_user.email,
        )

    # 2. Asynchronous External Email via Transactional Outbox
    if CommunicationChannel.EMAIL in effective_channels and recipient_email:
        rendered = render_template_for_intent(intent, context)

        # Check for existing pending/sent outbox message if idempotency key is given
        if idempotency_key:
            existing = OutboxMessage.objects.filter(
                idempotency_key=idempotency_key,
            ).first()
            if existing:
                results["outbox"] = str(existing.id)
                return results

        outbox_msg = OutboxMessage.objects.create(
            intent=intent,
            category=meta.category,
            recipient_email=recipient_email,
            recipient_user=recipient_user,
            subject=rendered.subject[:255],
            html_body=rendered.html_body,
            text_body=rendered.text_body,
            idempotency_key=idempotency_key,
            status=OutboxMessageStatus.PENDING,
        )
        results["outbox"] = str(outbox_msg.id)

        # Enqueue Celery delivery task safely on database transaction commit
        msg_id_str = str(outbox_msg.id)

        def _enqueue() -> None:
            try:
                deliver_outbox_message.delay(msg_id_str)
            except Exception as exc:
                logger.warning(
                    "Could not enqueue Celery delivery for outbox %s: %s",
                    msg_id_str,
                    exc,
                )

        transaction.on_commit(_enqueue)

    return results
