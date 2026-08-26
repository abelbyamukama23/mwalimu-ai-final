"""Delegated execution credential authentication for the Knowledge Gateway."""

from __future__ import annotations

import time
import uuid
from typing import Any

import jwt
from django.conf import settings
from rest_framework import authentication, exceptions

from platform_api.apps.users.models import User


def get_delegation_signing_key() -> str:
    """Return the configured signing key for delegated execution credentials."""
    return str(getattr(settings, "DELEGATION_SIGNING_KEY", settings.SECRET_KEY))


def mint_delegated_token(
    user_id: uuid.UUID | str,
    agent_run_id: uuid.UUID | str | None = None,
    session_id: uuid.UUID | str | None = None,
    expires_in_seconds: int = 900,
    knowledge_scope: str | None = None,
) -> str:
    """Mint a short-lived delegated execution token for Agent Service calls.

    Args:
        user_id: The execution identity (user on whose behalf agent acts).
        agent_run_id: Optional correlation identifier for the agent run.
        session_id: Optional correlation identifier for the user session.
        expires_in_seconds: Token lifetime in seconds (default 15 minutes).
        knowledge_scope: Optional authoritative knowledge scope for retrieval
            ("relevant" | "my" | "institution" | "public").

    Returns:
        Encoded and signed JWT string.
    """
    now = int(time.time())
    payload: dict[str, Any] = {
        "iss": "mwalimu-platform-api",
        "aud": "mwalimu-knowledge-gateway",
        "sub": str(user_id),
        "iat": now,
        "nbf": now,
        "exp": now + expires_in_seconds,
        "jti": str(uuid.uuid4()),
        "context": {
            "agent_run_id": str(agent_run_id) if agent_run_id else None,
            "session_id": str(session_id) if session_id else None,
            "delegated_by": "user_session",
            "knowledge_scope": knowledge_scope or "relevant",
        },
    }
    key = get_delegation_signing_key()
    return jwt.encode(payload, key, algorithm="HS256")


class DelegatedExecutionAuthentication(authentication.BaseAuthentication):
    """Authentication backend for short-lived delegated execution credentials.

    Validates HMAC-SHA256 JWT tokens issued by the Platform API to the Agent Service.
    Extracts the user_id (sub) as the execution identity without trusting any
    caller-supplied permissions.
    """

    def authenticate(self, request: Any) -> tuple[User, dict[str, Any]] | None:
        """Authenticate the request using a delegated execution credential."""
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Bearer "):
            return None

        raw_token = auth_header.split(" ", 1)[1].strip()
        key = get_delegation_signing_key()

        try:
            payload = jwt.decode(
                raw_token,
                key,
                algorithms=["HS256"],
                audience="mwalimu-knowledge-gateway",
                issuer="mwalimu-platform-api",
            )
        except jwt.ExpiredSignatureError as exc:
            raise exceptions.AuthenticationFailed(
                "Delegated execution token has expired."
            ) from exc
        except jwt.InvalidTokenError:
            # Not a valid delegated token; return None so standard
            # JWTAuthentication can try
            return None

        sub = payload.get("sub")
        if not sub:
            raise exceptions.AuthenticationFailed("Invalid token payload: missing sub.")

        try:
            user_uuid = uuid.UUID(str(sub))
            user = User.objects.get(pk=user_uuid, is_active=True)
        except (ValueError, User.DoesNotExist) as exc:
            raise exceptions.AuthenticationFailed(
                "Execution identity user not found or inactive."
            ) from exc

        return user, payload

    def authenticate_header(self, request: Any) -> str:
        """Return the WWW-Authenticate header string for 401 Unauthorized responses."""
        return 'Bearer realm="api"'
