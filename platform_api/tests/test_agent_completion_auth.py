"""Tests for Domain D internal service completion authentication backend."""

from __future__ import annotations

import time
import uuid

import jwt
import pytest
from django.test import RequestFactory
from rest_framework import exceptions

from platform_api.apps.agents.authentication import mint_platform_execution_jwt
from platform_api.apps.agents.completion_auth import (
    EXPECTED_AUDIENCE,
    EXPECTED_ISSUER,
    InternalServiceAuthentication,
    InternalServicePrincipal,
    get_internal_service_secret_key,
    mint_internal_service_jwt,
)
from platform_api.apps.knowledge.authentication import mint_delegated_token


@pytest.fixture
def auth_backend() -> InternalServiceAuthentication:
    """Create instance of InternalServiceAuthentication."""
    return InternalServiceAuthentication()


@pytest.fixture
def request_factory() -> RequestFactory:
    """Create request factory."""
    return RequestFactory()


def test_valid_domain_d_token_authenticates_successfully(
    auth_backend: InternalServiceAuthentication,
    request_factory: RequestFactory,
) -> None:
    """A valid Domain D token returns InternalServicePrincipal and claims."""
    token = mint_internal_service_jwt(sub="agent-service")
    request = request_factory.post(
        "/api/v1/internal/runs/123/completion/",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    result = auth_backend.authenticate(request)
    assert result is not None
    principal, claims = result
    assert isinstance(principal, InternalServicePrincipal)
    assert principal.is_authenticated is True
    assert principal.service_name == "agent-service"
    assert claims["iss"] == EXPECTED_ISSUER
    assert claims["aud"] == EXPECTED_AUDIENCE
    assert claims["sub"] == "agent-service"


def test_missing_auth_header_returns_none(
    auth_backend: InternalServiceAuthentication,
    request_factory: RequestFactory,
) -> None:
    """Missing Authorization header returns None."""
    request = request_factory.post("/api/v1/internal/runs/123/completion/")
    assert auth_backend.authenticate(request) is None


def test_malformed_auth_header_raises_authentication_failed(
    auth_backend: InternalServiceAuthentication,
    request_factory: RequestFactory,
) -> None:
    """Malformed header (not 'Bearer <token>') raises AuthenticationFailed."""
    request1 = request_factory.post(
        "/api/v1/internal/runs/123/completion/",
        HTTP_AUTHORIZATION="Basic dXNlcjpwYXNz",
    )
    with pytest.raises(
        exceptions.AuthenticationFailed, match="Expected 'Bearer <token>'"
    ):
        auth_backend.authenticate(request1)

    request2 = request_factory.post(
        "/api/v1/internal/runs/123/completion/",
        HTTP_AUTHORIZATION="Bearer",
    )
    with pytest.raises(
        exceptions.AuthenticationFailed, match="Expected 'Bearer <token>'"
    ):
        auth_backend.authenticate(request2)


def test_expired_domain_d_token_raises_authentication_failed(
    auth_backend: InternalServiceAuthentication,
    request_factory: RequestFactory,
) -> None:
    """An expired token raises AuthenticationFailed."""
    # Mint token that expired 10 seconds ago
    now = int(time.time())
    key = get_internal_service_secret_key()
    payload = {
        "iss": EXPECTED_ISSUER,
        "aud": EXPECTED_AUDIENCE,
        "sub": "agent-service",
        "iat": now - 30,
        "nbf": now - 30,
        "exp": now - 10,
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(payload, key, algorithm="HS256")
    request = request_factory.post(
        "/api/v1/internal/runs/123/completion/",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    with pytest.raises(exceptions.AuthenticationFailed, match="expired"):
        auth_backend.authenticate(request)


def test_invalid_signature_raises_authentication_failed(
    auth_backend: InternalServiceAuthentication,
    request_factory: RequestFactory,
) -> None:
    """Token signed with wrong key raises AuthenticationFailed."""
    token = mint_internal_service_jwt(
        secret_key="wrong-signing-secret-32-bytes-long-key!!"
    )
    request = request_factory.post(
        "/api/v1/internal/runs/123/completion/",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    with pytest.raises(exceptions.AuthenticationFailed, match="Invalid signature"):
        auth_backend.authenticate(request)


def test_wrong_issuer_rejected(
    auth_backend: InternalServiceAuthentication,
    request_factory: RequestFactory,
) -> None:
    """Token with wrong issuer (e.g. mwalimu-platform-api) is rejected."""
    key = get_internal_service_secret_key()
    now = int(time.time())
    payload = {
        "iss": "mwalimu-platform-api",  # Wrong issuer!
        "aud": EXPECTED_AUDIENCE,
        "sub": "agent-service",
        "iat": now,
        "exp": now + 60,
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(payload, key, algorithm="HS256")
    request = request_factory.post(
        "/api/v1/internal/runs/123/completion/",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    with pytest.raises(exceptions.AuthenticationFailed, match="Invalid token issuer"):
        auth_backend.authenticate(request)


def test_wrong_audience_rejected(
    auth_backend: InternalServiceAuthentication,
    request_factory: RequestFactory,
) -> None:
    """Token with wrong audience (e.g. mwalimu-knowledge-gateway) is rejected."""
    key = get_internal_service_secret_key()
    now = int(time.time())
    payload = {
        "iss": EXPECTED_ISSUER,
        "aud": "mwalimu-knowledge-gateway",  # Wrong audience!
        "sub": "agent-service",
        "iat": now,
        "exp": now + 60,
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(payload, key, algorithm="HS256")
    request = request_factory.post(
        "/api/v1/internal/runs/123/completion/",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    with pytest.raises(exceptions.AuthenticationFailed, match="Invalid token audience"):
        auth_backend.authenticate(request)


def test_platform_execution_jwt_rejected_by_internal_auth(
    auth_backend: InternalServiceAuthentication,
    request_factory: RequestFactory,
) -> None:
    """Platform Execution JWT (Domain B) is rejected by Domain D."""
    user_id = uuid.uuid4()
    domain_b_token = mint_platform_execution_jwt(user_id=user_id)
    request = request_factory.post(
        "/api/v1/internal/runs/123/completion/",
        HTTP_AUTHORIZATION=f"Bearer {domain_b_token}",
    )
    with pytest.raises(exceptions.AuthenticationFailed):
        auth_backend.authenticate(request)


def test_delegated_token_rejected_by_internal_auth(
    auth_backend: InternalServiceAuthentication,
    request_factory: RequestFactory,
) -> None:
    """DelegatedExecutionToken (Domain C) is rejected by Domain D."""
    user_id = uuid.uuid4()
    domain_c_token = mint_delegated_token(user_id=user_id)
    request = request_factory.post(
        "/api/v1/internal/runs/123/completion/",
        HTTP_AUTHORIZATION=f"Bearer {domain_c_token}",
    )
    with pytest.raises(exceptions.AuthenticationFailed):
        auth_backend.authenticate(request)
