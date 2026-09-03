"""Audit service for recording immutable institutional administrative events."""

from __future__ import annotations

from typing import Any
import uuid

from django.http import HttpRequest
from platform_api.apps.institutions.models import (
    AuditAction,
    Institution,
    InstitutionalAuditEvent,
)
from platform_api.apps.users.models import User


def get_client_ip(request: HttpRequest | None) -> str | None:
    """Extract client IP address from HTTP request."""
    if not request:
        return None
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def record_audit_event(
    institution: Institution,
    action: str | AuditAction,
    target_type: str,
    target_repr: str,
    actor: User | None = None,
    target_id: str | uuid.UUID = "",
    metadata: dict[str, Any] | None = None,
    request: HttpRequest | None = None,
) -> InstitutionalAuditEvent:
    """Record an immutable audit event in the institution's audit ledger."""
    clean_metadata: dict[str, Any] = {}
    if metadata:
        clean_metadata = {
            k: v
            for k, v in metadata.items()
            if k.lower() not in (
                "password",
                "secret",
                "token",
                "credentials",
                "encrypted_credentials",
                "authorization",
            )
        }

    ip = get_client_ip(request)

    return InstitutionalAuditEvent.objects.create(
        institution=institution,
        actor=actor,
        action=str(action),
        target_type=target_type,
        target_id=str(target_id) if target_id else "",
        target_repr=target_repr[:255],
        metadata=clean_metadata,
        ip_address=ip,
    )
