"""Tests for Delegated Execution Credential authentication."""

import time
import uuid

import jwt
import pytest
from django.test import RequestFactory
from rest_framework.exceptions import AuthenticationFailed

from platform_api.apps.knowledge.authentication import (
    DelegatedExecutionAuthentication,
    get_delegation_signing_key,
    mint_delegated_token,
)
from platform_api.apps.users.models import User


@pytest.fixture
def auth_backend() -> DelegatedExecutionAuthentication:
    """Return an instance of DelegatedExecutionAuthentication."""
    return DelegatedExecutionAuthentication()


@pytest.fixture
def rf() -> RequestFactory:
    """Return a Django request factory."""
    return RequestFactory()


@pytest.mark.django_db
def test_valid_delegated_token_authenticates_execution_identity(
    auth_backend: DelegatedExecutionAuthentication,
    rf: RequestFactory,
    user_a: User,
) -> None:
    """Valid delegated execution token correctly resolves the user and audit context."""
    agent_run_id = uuid.uuid4()
    session_id = uuid.uuid4()

    token = mint_delegated_token(
        user_id=user_a.id,
        agent_run_id=agent_run_id,
        session_id=session_id,
        expires_in_seconds=600,
    )

    request = rf.post("/api/v1/knowledge/search/", HTTP_AUTHORIZATION=f"Bearer {token}")
    auth_result = auth_backend.authenticate(request)

    assert auth_result is not None
    authenticated_user, payload = auth_result

    assert authenticated_user == user_a
    assert payload["sub"] == str(user_a.id)
    assert payload["context"]["agent_run_id"] == str(agent_run_id)
    assert payload["context"]["session_id"] == str(session_id)


@pytest.mark.django_db
def test_expired_delegated_token_raises_authentication_failed(
    auth_backend: DelegatedExecutionAuthentication,
    rf: RequestFactory,
    user_a: User,
) -> None:
    """Expired delegated execution token fails authentication."""
    # Mint expired token (expired 10 seconds ago)
    token = mint_delegated_token(user_id=user_a.id, expires_in_seconds=-10)

    request = rf.post("/api/v1/knowledge/search/", HTTP_AUTHORIZATION=f"Bearer {token}")
    with pytest.raises(AuthenticationFailed, match="expired"):
        auth_backend.authenticate(request)


@pytest.mark.django_db
def test_invalid_audience_returns_none_for_fallback(
    auth_backend: DelegatedExecutionAuthentication,
    rf: RequestFactory,
    user_a: User,
) -> None:
    """Token with wrong audience returns None to allow regular JWT auth fallback."""
    now = int(time.time())
    payload = {
        "iss": "mwalimu-platform-api",
        "aud": "wrong-audience",
        "sub": str(user_a.id),
        "iat": now,
        "exp": now + 600,
    }
    key = get_delegation_signing_key()
    token = jwt.encode(payload, key, algorithm="HS256")

    request = rf.post("/api/v1/knowledge/search/", HTTP_AUTHORIZATION=f"Bearer {token}")
    result = auth_backend.authenticate(request)
    assert result is None


@pytest.mark.django_db
def test_inactive_user_raises_authentication_failed(
    auth_backend: DelegatedExecutionAuthentication,
    rf: RequestFactory,
    user_a: User,
) -> None:
    """Delegated token for an inactive user is rejected."""
    user_a.is_active = False
    user_a.save(update_fields=["is_active"])

    token = mint_delegated_token(user_id=user_a.id)
    request = rf.post("/api/v1/knowledge/search/", HTTP_AUTHORIZATION=f"Bearer {token}")

    with pytest.raises(AuthenticationFailed, match="inactive"):
        auth_backend.authenticate(request)


@pytest.mark.django_db
def test_non_bearer_header_returns_none(
    auth_backend: DelegatedExecutionAuthentication,
    rf: RequestFactory,
) -> None:
    """Missing or non-bearer auth header returns None."""
    request = rf.post("/api/v1/knowledge/search/")
    assert auth_backend.authenticate(request) is None

    request_basic = rf.post(
        "/api/v1/knowledge/search/", HTTP_AUTHORIZATION="Basic abcdef"
    )
    assert auth_backend.authenticate(request_basic) is None
