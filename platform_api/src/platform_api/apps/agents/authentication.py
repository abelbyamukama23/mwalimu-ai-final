"""Authentication and token minting for Platform API -> Agent Service dispatch."""

from __future__ import annotations

import time
import uuid
from typing import Any

import jwt
from django.conf import settings


def get_agent_service_jwt_secret_key() -> str:
    """Return the configured signing key for Platform -> Agent Service JWTs."""
    return str(
        getattr(
            settings,
            "AGENT_SERVICE_JWT_SECRET_KEY",
            "mwalimu-insecure-dev-secret-key-change-in-production",
        )
    )


def mint_platform_execution_jwt(
    user_id: uuid.UUID | str,
    expires_in_seconds: int | None = None,
) -> str:
    """Mint a short-lived Platform Execution JWT for authenticating to Agent Service.

    Domain B Credential:
    - Issuer: "mwalimu-platform-api"
    - Audience: "mwalimu-agent-service"
    - Subject: User UUID string
    - Lifetime: Configurable (default 300 seconds)

    Args:
        user_id: The authenticated user on whose behalf execution is requested.
        expires_in_seconds: Optional token lifetime in seconds.

    Returns:
        Encoded and signed JWT string.
    """
    now = int(time.time())
    ttl = (
        expires_in_seconds
        if expires_in_seconds is not None
        else int(getattr(settings, "AGENT_SERVICE_JWT_EXPIRATION_SECONDS", 300))
    )
    payload: dict[str, Any] = {
        "iss": "mwalimu-platform-api",
        "aud": "mwalimu-agent-service",
        "sub": str(user_id),
        "iat": now,
        "nbf": now,
        "exp": now + ttl,
        "jti": str(uuid.uuid4()),
    }
    key = get_agent_service_jwt_secret_key()
    algorithm = getattr(settings, "AGENT_SERVICE_JWT_ALGORITHM", "HS256")
    return jwt.encode(payload, key, algorithm=algorithm)


def get_agent_stream_signing_key() -> str:
    """Return the configured signing key for Domain S stream capability tokens."""
    return str(
        getattr(
            settings,
            "AGENT_STREAM_JWT_SECRET_KEY",
            getattr(
                settings,
                "AGENT_SERVICE_JWT_SECRET_KEY",
                "mwalimu-insecure-dev-secret-key-change-in-production",
            ),
        )
    )


def mint_streaming_ticket(
    user_id: uuid.UUID | str,
    run_id: uuid.UUID | str,
    session_id: uuid.UUID | str,
    expires_in_seconds: int | None = None,
) -> str:
    """Mint a short-lived Domain S Stream Capability Token for native SSE streaming.

    Domain S Credential:
    - Purpose: Read-only streaming access to one specific agent run.
    - Issuer: "mwalimu-platform-api"
    - Audience: "mwalimu-agent-stream"
    - Subject: User UUID string (user-bound)
    - run_id: Run UUID string (run-bound)
    - session_id: Session UUID string (session-bound)
    - scope: "run:stream" (read-only, scoped)
    - Lifetime: Configurable (default 300 seconds)

    Args:
        user_id: The authenticated user UUID.
        run_id: The durable AgentRunRecord UUID.
        session_id: The parent AgentSession UUID.
        expires_in_seconds: Optional token lifetime in seconds.

    Returns:
        Encoded and signed JWT string.
    """
    now = int(time.time())
    ttl = (
        expires_in_seconds
        if expires_in_seconds is not None
        else int(getattr(settings, "AGENT_STREAM_JWT_EXPIRATION_SECONDS", 300))
    )
    payload: dict[str, Any] = {
        "iss": "mwalimu-platform-api",
        "aud": "mwalimu-agent-stream",
        "sub": str(user_id),
        "run_id": str(run_id),
        "session_id": str(session_id),
        "scope": "run:stream",
        "iat": now,
        "nbf": now,
        "exp": now + ttl,
        "jti": str(uuid.uuid4()),
    }
    key = get_agent_stream_signing_key()
    algorithm = getattr(
        settings,
        "AGENT_STREAM_JWT_ALGORITHM",
        getattr(settings, "AGENT_SERVICE_JWT_ALGORITHM", "HS256"),
    )
    return jwt.encode(payload, key, algorithm=algorithm)
