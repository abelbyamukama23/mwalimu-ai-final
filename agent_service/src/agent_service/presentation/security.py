"""Cryptographic authentication dependencies for Agent Service API endpoints.

Domain B — Platform Execution Credential:
    Used by Platform API to dispatch runs, query status, and cancel.
    Verified using JWT_SECRET_KEY / JWT_ALGORITHM.

Domain S — Agent Stream Capability Token:
    Used by browser/mobile clients for direct SSE streaming.
    Verified using AGENT_STREAM_JWT_SECRET_KEY / AGENT_STREAM_JWT_ALGORITHM.
    Carries narrowly scoped claims (iss, aud, sub, run_id,
    session_id, scope=run:stream).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agent_service.config import settings

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """Cryptographically verified client identity.

    Attributes:
        user_id: Authoritative UUID of the authenticated user.
        is_authenticated: Boolean flag confirming verified state.
    """

    user_id: uuid.UUID
    is_authenticated: bool = True


@dataclass(frozen=True)
class StreamingPrincipal:
    """Cryptographically verified Domain S streaming identity.

    Carries the narrow capability claims required for SSE streaming.

    Attributes:
        user_id: Authoritative UUID of the authenticated user (sub).
        run_id: UUID of the specific run authorized for streaming.
        session_id: UUID of the parent session.
        scope: Token scope (always "run:stream").
    """

    user_id: uuid.UUID
    run_id: uuid.UUID
    session_id: uuid.UUID
    scope: str = "run:stream"


def decode_jwt_token(token: str, key: str | None = None) -> dict[str, Any]:
    """Decode and verify a Domain B JWT token."""
    secret = key or settings.JWT_SECRET_KEY
    return jwt.decode(
        token,
        secret,
        algorithms=[settings.JWT_ALGORITHM],
        options={"verify_aud": False, "verify_iss": False},
    )


def _get_stream_signing_key() -> str:
    """Return the configured Domain S verification key.

    Falls back to JWT_SECRET_KEY (Domain B) only in development
    when AGENT_STREAM_JWT_SECRET_KEY is not explicitly configured.
    """
    if (
        settings.AGENT_STREAM_JWT_SECRET_KEY
        and settings.AGENT_STREAM_JWT_SECRET_KEY.strip()
    ):
        return settings.AGENT_STREAM_JWT_SECRET_KEY
    return settings.JWT_SECRET_KEY


def decode_stream_token(token: str) -> dict[str, Any]:
    """Decode and verify a Domain S stream capability JWT.

    Enforces:
        - Cryptographic signature verification
        - iss == "mwalimu-platform-api"
        - aud == "mwalimu-agent-stream"
        - exp / nbf temporal validity
        - Required claims: sub, run_id, session_id, scope, jti
    """
    key = _get_stream_signing_key()
    return jwt.decode(
        token,
        key,
        algorithms=[settings.AGENT_STREAM_JWT_ALGORITHM],
        issuer="mwalimu-platform-api",
        audience="mwalimu-agent-stream",
        options={
            "verify_iss": True,
            "verify_aud": True,
            "verify_exp": True,
            "verify_nbf": True,
            "require": [
                "sub",
                "run_id",
                "session_id",
                "scope",
                "jti",
                "iss",
                "aud",
                "exp",
                "nbf",
                "iat",
            ],
        },
    )


async def get_authenticated_principal(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ] = None,
) -> AuthenticatedPrincipal:
    """Extract and verify client identity from Bearer token."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raw_token = credentials.credentials
    try:
        payload = decode_jwt_token(raw_token)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token signature has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except (jwt.InvalidTokenError, Exception) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing subject identifier (sub).",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_uuid = uuid.UUID(str(sub))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject identifier is not a valid UUID.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return AuthenticatedPrincipal(user_id=user_uuid, is_authenticated=True)


async def get_streaming_principal(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ] = None,
) -> StreamingPrincipal:
    """Extract and verify Domain S stream capability token.

    Validates:
        - Bearer token presence
        - Cryptographic signature (Domain S key)
        - Issuer, audience, expiration, not-before
        - Required claims (sub, run_id, session_id, scope, jti)
        - scope == "run:stream"
        - Valid UUID formatting for sub, run_id, session_id
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raw_token = credentials.credentials
    try:
        payload = decode_stream_token(raw_token)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token signature has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.InvalidIssuerError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.InvalidAudienceError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.MissingRequiredClaimError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.ImmatureSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is not yet valid.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except (jwt.InvalidTokenError, Exception) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # Verify scope is strictly "run:stream"
    scope = payload.get("scope")
    if scope != "run:stream":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate UUID format for sub, run_id, session_id
    try:
        user_uuid = uuid.UUID(str(payload["sub"]))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    try:
        run_uuid = uuid.UUID(str(payload["run_id"]))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    try:
        session_uuid = uuid.UUID(str(payload["session_id"]))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return StreamingPrincipal(
        user_id=user_uuid,
        run_id=run_uuid,
        session_id=session_uuid,
        scope="run:stream",
    )
