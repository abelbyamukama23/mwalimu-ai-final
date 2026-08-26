"""Unit and integration tests for Domain S Agent Stream Capability Tokens.

Tests cover:
- Token claim verification (iss, aud, scope, sub, run_id, session_id,
  jti, iat, nbf, exp)
- Cryptographic signature validation and rejection with wrong key
- Token expiration behavior
- Serializer backward compatibility with and without streaming descriptor
- SessionRunCreateView integration returning streaming descriptor on 202
- Dispatch failure behavior (no token minted / error handled)
"""

from __future__ import annotations

import time
import uuid
from unittest.mock import patch

import jwt
import pytest
from rest_framework.test import APIClient

from platform_api.apps.agents.authentication import (
    get_agent_stream_signing_key,
    mint_streaming_ticket,
)
from platform_api.apps.agents.client import (
    AgentServiceClient,
    AgentServiceConnectionError,
    AgentServiceRunResponse,
)
from platform_api.apps.agents.models import (
    AgentRunRecord,
    AgentRunStatus,
    AgentSession,
    AgentSessionStatus,
)
from platform_api.apps.agents.orchestration import AgentServiceUnavailableError
from platform_api.apps.agents.serializers import (
    RunResponseSerializer,
    StreamingDescriptorSerializer,
)
from platform_api.apps.institutions.models import Institution, InstitutionStatus
from platform_api.apps.memberships.models import Membership
from platform_api.apps.users.models import User

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def institution(db: None) -> Institution:
    """Return an active test institution."""
    return Institution.objects.create(
        name="Stream Tech University",
        slug="stream-tech-uni",
        status=InstitutionStatus.ACTIVE,
    )


@pytest.fixture
def user(db: None) -> User:
    """Return a test user."""
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        email="streamer@example.com",
        password="test-stream-password-123",
    )


@pytest.fixture
def membership(user: User, institution: Institution) -> Membership:
    """Return an active membership."""
    return Membership.objects.create(
        user=user,
        institution=institution,
        role="student",
    )


@pytest.fixture
def session(user: User, institution: Institution) -> AgentSession:
    """Return an active session."""
    return AgentSession.objects.create(
        user=user,
        institution=institution,
        title="Streaming Session",
        status=AgentSessionStatus.ACTIVE,
    )


@pytest.fixture
def run_record(session: AgentSession, user: User) -> AgentRunRecord:
    """Return a queued run record."""
    return AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Explain quantum entanglement",
        status=AgentRunStatus.QUEUED,
    )


@pytest.fixture
def auth_client(user: User) -> APIClient:
    """Return an authenticated API client."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _mock_dispatch_response(prompt: str = "Test prompt") -> AgentServiceRunResponse:
    """Return a mock successful AgentServiceRunResponse."""
    return AgentServiceRunResponse(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        status="queued",
        prompt=prompt,
        created_at="2026-08-24T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# 1. Token Minting and Claims Tests
# ---------------------------------------------------------------------------


def test_mint_streaming_ticket_claims() -> None:
    """Token contains exact required claims for Domain S capability."""
    user_id = uuid.uuid4()
    run_id = uuid.uuid4()
    session_id = uuid.uuid4()

    before_mint = int(time.time())
    token = mint_streaming_ticket(
        user_id=user_id,
        run_id=run_id,
        session_id=session_id,
        expires_in_seconds=300,
    )
    after_mint = int(time.time())

    key = get_agent_stream_signing_key()
    payload = jwt.decode(
        token,
        key,
        algorithms=["HS256"],
        audience="mwalimu-agent-stream",
        issuer="mwalimu-platform-api",
    )

    # Core claim assertions
    assert payload["iss"] == "mwalimu-platform-api"
    assert payload["aud"] == "mwalimu-agent-stream"
    assert payload["scope"] == "run:stream"
    assert payload["sub"] == str(user_id)
    assert payload["run_id"] == str(run_id)
    assert payload["session_id"] == str(session_id)

    # JTI uniqueness
    assert isinstance(payload["jti"], str)
    uuid.UUID(payload["jti"])  # Validates UUID format

    # Timestamps
    assert before_mint <= payload["iat"] <= after_mint
    assert payload["nbf"] == payload["iat"]
    assert payload["exp"] == payload["iat"] + 300


def test_mint_streaming_ticket_unique_jti() -> None:
    """Subsequent mints produce distinct unique jti values."""
    user_id = uuid.uuid4()
    run_id = uuid.uuid4()
    session_id = uuid.uuid4()

    token1 = mint_streaming_ticket(user_id, run_id, session_id)
    token2 = mint_streaming_ticket(user_id, run_id, session_id)

    key = get_agent_stream_signing_key()
    p1 = jwt.decode(token1, key, algorithms=["HS256"], audience="mwalimu-agent-stream")
    p2 = jwt.decode(token2, key, algorithms=["HS256"], audience="mwalimu-agent-stream")

    assert p1["jti"] != p2["jti"]


def test_mint_streaming_ticket_custom_expiry() -> None:
    """Custom expiration lifetime is respected in exp claim."""
    user_id = uuid.uuid4()
    run_id = uuid.uuid4()
    session_id = uuid.uuid4()

    token = mint_streaming_ticket(user_id, run_id, session_id, expires_in_seconds=600)
    key = get_agent_stream_signing_key()
    payload = jwt.decode(
        token, key, algorithms=["HS256"], audience="mwalimu-agent-stream"
    )

    assert payload["exp"] == payload["iat"] + 600


# ---------------------------------------------------------------------------
# 2. Cryptographic Signature & Expiration Tests
# ---------------------------------------------------------------------------


def test_signature_verification_failure_with_wrong_key() -> None:
    """Verifying token with wrong secret key fails with InvalidSignatureError."""
    token = mint_streaming_ticket(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())

    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(
            token,
            "wrong-secret-key-that-is-at-least-32-bytes-long-for-sha256!",
            algorithms=["HS256"],
            audience="mwalimu-agent-stream",
        )


def test_expired_token_raises_expired_signature_error() -> None:
    """An expired token raises jwt.ExpiredSignatureError."""
    token = mint_streaming_ticket(
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
        expires_in_seconds=-10,  # Expired 10 seconds ago
    )
    key = get_agent_stream_signing_key()

    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(
            token,
            key,
            algorithms=["HS256"],
            audience="mwalimu-agent-stream",
        )


def test_audience_mismatch_rejected() -> None:
    """Verifying token with wrong expected audience fails."""
    token = mint_streaming_ticket(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
    key = get_agent_stream_signing_key()

    with pytest.raises(jwt.InvalidAudienceError):
        jwt.decode(
            token,
            key,
            algorithms=["HS256"],
            audience="mwalimu-agent-service",  # Wrong audience
        )


def test_issuer_mismatch_rejected() -> None:
    """Verifying token with wrong expected issuer fails."""
    token = mint_streaming_ticket(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
    key = get_agent_stream_signing_key()

    with pytest.raises(jwt.InvalidIssuerError):
        jwt.decode(
            token,
            key,
            algorithms=["HS256"],
            audience="mwalimu-agent-stream",
            issuer="wrong-issuer",
        )


def test_scope_claim_is_strictly_run_stream() -> None:
    """Token scope is strictly 'run:stream' for read-only streaming access."""
    token = mint_streaming_ticket(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
    key = get_agent_stream_signing_key()
    payload = jwt.decode(
        token, key, algorithms=["HS256"], audience="mwalimu-agent-stream"
    )

    assert payload["scope"] == "run:stream"
    assert "admin" not in payload["scope"]
    assert "write" not in payload["scope"]


# ---------------------------------------------------------------------------
# 3. Serializer Backward Compatibility Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_run_response_serializer_without_streaming(
    run_record: AgentRunRecord,
) -> None:
    """RunResponseSerializer serializes streaming as None when not populated."""
    serializer = RunResponseSerializer(run_record)
    data = serializer.data

    assert data["id"] == str(run_record.id)
    assert data["status"] == "queued"
    assert data["prompt"] == "Explain quantum entanglement"
    assert data["streaming"] is None


@pytest.mark.django_db
def test_run_response_serializer_with_streaming(
    run_record: AgentRunRecord,
) -> None:
    """RunResponseSerializer includes streaming descriptor when populated."""
    ticket = mint_streaming_ticket(
        user_id=run_record.user.pk,
        run_id=run_record.pk,
        session_id=run_record.session.pk,
    )
    run_record.streaming = {  # type: ignore[attr-defined]
        "sse_url": f"http://localhost:8001/api/v1/runs/{run_record.id}/events",
        "ticket": ticket,
        "expires_in": 300,
    }

    serializer = RunResponseSerializer(run_record)
    data = serializer.data

    assert data["streaming"] is not None
    assert (
        data["streaming"]["sse_url"]
        == f"http://localhost:8001/api/v1/runs/{run_record.id}/events"
    )
    assert data["streaming"]["ticket"] == ticket
    assert data["streaming"]["expires_in"] == 300


def test_streaming_descriptor_serializer_validation() -> None:
    """StreamingDescriptorSerializer validates required fields."""
    valid_data = {
        "sse_url": "http://localhost:8001/api/v1/runs/123/events",
        "ticket": "jwt-ticket-token",
        "expires_in": 300,
    }
    serializer = StreamingDescriptorSerializer(data=valid_data)
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["expires_in"] == 300


# ---------------------------------------------------------------------------
# 4. View Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_session_run_create_view_returns_streaming_descriptor(
    auth_client: APIClient,
    session: AgentSession,
    user: User,
    membership: Membership,
) -> None:
    """Successful run submission returns 202 with Domain S streaming descriptor."""
    payload = {
        "prompt": "What is cellular respiration?",
        "max_steps": 5,
        "timeout_seconds": 45.0,
    }

    with patch.object(
        AgentServiceClient,
        "dispatch_run",
        return_value=_mock_dispatch_response("What is cellular respiration?"),
    ):
        response = auth_client.post(
            f"/api/v1/sessions/{session.id}/runs/",
            payload,
            format="json",
        )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "queued"
    assert data["prompt"] == "What is cellular respiration?"
    assert data["session_id"] == str(session.id)

    # Verify streaming descriptor
    assert "streaming" in data
    streaming = data["streaming"]
    assert streaming is not None
    assert "sse_url" in streaming
    assert "ticket" in streaming
    assert streaming["expires_in"] == 300

    # Verify the ticket is valid and decodable with expected claims
    ticket = streaming["ticket"]
    key = get_agent_stream_signing_key()
    claims = jwt.decode(
        ticket,
        key,
        algorithms=["HS256"],
        audience="mwalimu-agent-stream",
        issuer="mwalimu-platform-api",
    )
    assert claims["sub"] == str(user.pk)
    assert claims["run_id"] == data["id"]
    assert claims["session_id"] == str(session.id)
    assert claims["scope"] == "run:stream"


@pytest.mark.django_db
def test_dispatch_failure_does_not_issue_streaming_ticket(
    auth_client: APIClient,
    session: AgentSession,
    membership: Membership,
) -> None:
    """When dispatch fails, run is marked FAILED and exception is raised."""
    payload = {"prompt": "This dispatch will fail"}

    with (
        patch.object(
            AgentServiceClient,
            "dispatch_run",
            side_effect=AgentServiceConnectionError("Connection refused"),
        ),
        pytest.raises(AgentServiceUnavailableError),
    ):
        auth_client.post(
            f"/api/v1/sessions/{session.id}/runs/",
            payload,
            format="json",
        )

    # Verify the created run was transitioned to FAILED in PostgreSQL
    failed_run = AgentRunRecord.objects.filter(session=session).latest("created_at")
    assert failed_run.status == AgentRunStatus.FAILED
    assert failed_run.error_code == "AGENT_SERVICE_UNAVAILABLE"
