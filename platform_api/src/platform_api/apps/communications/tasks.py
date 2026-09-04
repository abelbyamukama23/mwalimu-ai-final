"""Celery tasks for delivering outbox messages asynchronously."""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task
from django.conf import settings
from django.utils import timezone
import httpx

from .models import OutboxMessage, OutboxMessageStatus

logger = logging.getLogger(__name__)

RESEND_API_ENDPOINT = "https://api.resend.com/emails"


def _send_via_resend(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: str | None = None,
) -> dict[str, Any]:
    """Execute delivery via Resend API or mock in test/sandbox."""
    api_key = getattr(settings, "RESEND_API_KEY", "").strip()
    from_email = getattr(
        settings, "EMAIL_FROM", "Mwalimu <onboarding@resend.dev>"
    )

    if not api_key or api_key == "mock" or api_key.startswith("re_mock_"):
        logger.info(
            "Mocked delivery to %s for subject: '%s'",
            to_email,
            subject,
        )
        return {"id": "mock_email_id", "simulated": True}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "html": html_content,
    }
    if text_content:
        payload["text"] = text_content

    with httpx.Client(timeout=10.0) as client:
        response = client.post(
            RESEND_API_ENDPOINT,
            headers=headers,
            json=payload,
        )
        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"Resend HTTP {response.status_code}: {response.text}"
            )
        return response.json()  # type: ignore[no-any-return]


@shared_task(bind=True, max_retries=5, default_retry_delay=60)
def deliver_outbox_message(self: Any, message_id: str) -> None:
    """Asynchronously deliver a queued outbox message."""
    try:
        msg = OutboxMessage.objects.get(pk=message_id)
    except OutboxMessage.DoesNotExist:
        logger.warning("OutboxMessage %s does not exist; skipping delivery.", message_id)
        return

    if msg.status == OutboxMessageStatus.SENT:
        return

    msg.attempts += 1
    msg.last_attempt_at = timezone.now()

    try:
        res = _send_via_resend(
            to_email=msg.recipient_email,
            subject=msg.subject,
            html_content=msg.html_body,
            text_content=msg.text_body,
        )
        msg.status = OutboxMessageStatus.SENT
        msg.sent_at = timezone.now()
        msg.external_reference = str(res.get("id", ""))
        msg.error_message = ""
        msg.save(
            update_fields=[
                "status",
                "sent_at",
                "external_reference",
                "attempts",
                "last_attempt_at",
                "error_message",
                "updated_at",
            ]
        )
        logger.info(
            "Successfully delivered outbox message %s (%s) to %s",
            msg.id,
            msg.intent,
            msg.recipient_email,
        )
    except Exception as exc:
        msg.error_message = str(exc)
        if msg.attempts >= msg.max_attempts:
            msg.status = OutboxMessageStatus.FAILED
            logger.error(
                "Outbox message %s permanently failed after %d attempts: %s",
                msg.id,
                msg.attempts,
                exc,
            )
        else:
            msg.status = OutboxMessageStatus.RETRYING
            logger.warning(
                "Outbox message %s delivery error on attempt %d: %s; retrying...",
                msg.id,
                msg.attempts,
                exc,
            )
        msg.save(
            update_fields=[
                "status",
                "attempts",
                "last_attempt_at",
                "error_message",
                "updated_at",
            ]
        )
        if msg.status == OutboxMessageStatus.RETRYING:
            raise self.retry(exc=exc, countdown=min(60 * (2 ** msg.attempts), 3600))
