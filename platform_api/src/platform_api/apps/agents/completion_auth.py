"""Internal service authentication for Agent Service completion callbacks.

Domain D Credential:
- Issuer: "mwalimu-agent-service"
- Audience: "mwalimu-platform-internal"
- Subject: "agent-service" (or caller-provided internal service identity)
- Lifetime: Short-lived (default 60s)
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

import jwt
from django.conf import settings
from rest_framework import authentication, exceptions

logger = logging.getLogger(__name__)

EXPECTED_ISSUER = "mwalimu-agent-service"
EXPECTED_AUDIENCE = "mwalimu-platform-internal"


def get_internal_service_secret_key() -> str:
    """Return the configured signing secret for Domain D internal service JWTs."""
    return str(
        getattr(
            settings,
            "INTERNAL_SERVICE_SECRET_KEY",
            "mwalimu-insecure-dev-internal-secret-change-in-production",
        )
    )


def mint_internal_service_jwt(
    secret_key: str | None = None,
    algorithm: str | None = None,
    expires_in_seconds: int = 60,
    sub: str = "agent-service",
) -> str:
    """Mint a Domain D internal service JWT for completion callback testing.

    Args:
        secret_key: Optional signing key (defaults to settings).
        algorithm: Optional algorithm (defaults to settings).
        expires_in_seconds: Token TTL in seconds.
        sub: Subject claim.

    Returns:
        Encoded signed JWT.
    """
    key = secret_key if secret_key is not None else get_internal_service_secret_key()
    algo = algorithm or getattr(settings, "INTERNAL_SERVICE_JWT_ALGORITHM", "HS256")
    now = int(time.time())
    payload: dict[str, Any] = {
        "iss": EXPECTED_ISSUER,
        "aud": EXPECTED_AUDIENCE,
        "sub": sub,
        "iat": now,
        "nbf": now,
        "exp": now + expires_in_seconds,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, key, algorithm=algo)


@dataclass(frozen=True)
class InternalServicePrincipal:
    """Authenticated principal representing an authorized internal service."""

    service_name: str
    is_authenticated: bool = True
    is_anonymous: bool = False

    def __str__(self) -> str:
        """Return string representation."""
        return f"InternalServicePrincipal({self.service_name})"


class InternalServiceAuthentication(authentication.BaseAuthentication):
    """DRF Authentication backend for Domain D internal service credentials.

    Enforces that incoming requests possess a valid short-lived JWT issued
    by Agent Service for the Platform API internal audience.
    """

    def authenticate(
        self, request: Any
    ) -> tuple[InternalServicePrincipal, dict[str, Any]] | None:
        """Authenticate the request using the Authorization Bearer header.

        Returns:
            Tuple of (InternalServicePrincipal, decoded_claims) if valid,
            or None if no Authorization header is present.

        Raises:
            exceptions.AuthenticationFailed: If the token is invalid or expired.
        """
        auth_header = request.headers.get("Authorization") or request.META.get(
            "HTTP_AUTHORIZATION"
        )
        if not auth_header:
            return None

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise exceptions.AuthenticationFailed(
                "Invalid Authorization header format. Expected 'Bearer <token>'."
            )

        token = parts[1]
        key = get_internal_service_secret_key()
        algorithm = getattr(settings, "INTERNAL_SERVICE_JWT_ALGORITHM", "HS256")

        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=[algorithm],
                issuer=EXPECTED_ISSUER,
                audience=EXPECTED_AUDIENCE,
                options={
                    "require": ["exp", "iss", "aud", "sub"],
                    "verify_exp": True,
                    "verify_iss": True,
                    "verify_aud": True,
                },
            )
        except jwt.ExpiredSignatureError as exc:
            raise exceptions.AuthenticationFailed(
                "Internal service token has expired."
            ) from exc
        except jwt.InvalidIssuerError as exc:
            raise exceptions.AuthenticationFailed(
                "Invalid token issuer for internal service endpoint."
            ) from exc
        except jwt.InvalidAudienceError as exc:
            raise exceptions.AuthenticationFailed(
                "Invalid token audience for internal service endpoint."
            ) from exc
        except jwt.InvalidSignatureError as exc:
            raise exceptions.AuthenticationFailed(
                "Invalid signature on internal service token."
            ) from exc
        except jwt.DecodeError as exc:
            raise exceptions.AuthenticationFailed(
                "Malformed internal service token."
            ) from exc
        except Exception as exc:
            raise exceptions.AuthenticationFailed(
                f"Internal service authentication error: {exc}"
            ) from exc

        sub = str(claims.get("sub", "")).strip()
        if not sub:
            raise exceptions.AuthenticationFailed(
                "Internal service token missing valid subject."
            )

        principal = InternalServicePrincipal(service_name=sub)
        return principal, claims

    def authenticate_header(self, request: Any) -> str:
        """Return Bearer challenge header for 401 responses."""
        return 'Bearer realm="mwalimu-platform-internal"'
