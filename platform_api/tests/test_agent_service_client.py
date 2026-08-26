"""Tests for the AgentServiceClient and Platform Execution JWT authentication."""

from __future__ import annotations

import uuid

import httpx
import jwt
import pytest
from django.conf import settings

from platform_api.apps.agents.authentication import (
    get_agent_service_jwt_secret_key,
    mint_platform_execution_jwt,
)
from platform_api.apps.agents.client import (
    AgentServiceCancelResponse,
    AgentServiceClient,
    AgentServiceConnectionError,
    AgentServiceResponseError,
    AgentServiceRunResponse,
    AgentServiceTimeoutError,
    AgentServiceValidationError,
)
from platform_api.apps.knowledge.authentication import (
    get_delegation_signing_key,
    mint_delegated_token,
)

# ---------------------------------------------------------------------------
# Platform Execution JWT Tests (Domain B)
# ---------------------------------------------------------------------------


def test_mint_platform_execution_jwt_claims() -> None:
    """Platform Execution JWT contains expected claims for Agent Service."""
    user_id = uuid.uuid4()
    token = mint_platform_execution_jwt(user_id=user_id, expires_in_seconds=300)

    key = get_agent_service_jwt_secret_key()
    payload = jwt.decode(
        token,
        key,
        algorithms=["HS256"],
        options={"verify_aud": False, "verify_iss": False},
    )

    assert payload["iss"] == "mwalimu-platform-api"
    assert payload["aud"] == "mwalimu-agent-service"
    assert payload["sub"] == str(user_id)
    assert "jti" in payload
    assert payload["exp"] - payload["iat"] == 300


def test_platform_jwt_is_verifiable_by_agent_service_decoder() -> None:
    """The token minted by Platform API can be decoded with Agent Service logic."""
    user_id = uuid.uuid4()
    token = mint_platform_execution_jwt(user_id=user_id)

    # Replicate Agent Service decoding logic
    key = get_agent_service_jwt_secret_key()
    payload = jwt.decode(
        token,
        key,
        algorithms=["HS256"],
        options={"verify_aud": False, "verify_iss": False},
    )
    assert uuid.UUID(payload["sub"]) == user_id


def test_distinct_credential_domains() -> None:
    """Platform Execution JWT (Domain B) and Delegated token (Domain C) are distinct."""
    user_id = uuid.uuid4()
    run_id = uuid.uuid4()
    session_id = uuid.uuid4()

    platform_jwt = mint_platform_execution_jwt(user_id=user_id)
    delegated_token = mint_delegated_token(
        user_id=user_id, agent_run_id=run_id, session_id=session_id
    )

    # Domain B: aud = mwalimu-agent-service
    p_payload = jwt.decode(
        platform_jwt,
        get_agent_service_jwt_secret_key(),
        algorithms=["HS256"],
        options={"verify_aud": False},
    )
    assert p_payload["aud"] == "mwalimu-agent-service"

    # Domain C: aud = mwalimu-knowledge-gateway
    d_payload = jwt.decode(
        delegated_token,
        get_delegation_signing_key(),
        algorithms=["HS256"],
        options={"verify_aud": False},
    )
    assert d_payload["aud"] == "mwalimu-knowledge-gateway"
    assert d_payload["context"]["agent_run_id"] == str(run_id)

    # They cannot be used interchangeably
    assert platform_jwt != delegated_token


# ---------------------------------------------------------------------------
# AgentServiceClient Mock Transport Tests
# ---------------------------------------------------------------------------


def test_client_successful_dispatch() -> None:
    """AgentServiceClient successfully dispatches a run to the Agent Service."""
    run_id = uuid.uuid4()
    session_id = uuid.uuid4()
    user_id = uuid.uuid4()

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v1/runs"
        assert "Authorization" in request.headers
        assert request.headers["Authorization"].startswith("Bearer ")
        assert request.headers["Accept"] == "application/json"

        # Verify Bearer token contains correct user_id
        raw_jwt = request.headers["Authorization"].split(" ")[1]
        payload = jwt.decode(
            raw_jwt,
            get_agent_service_jwt_secret_key(),
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        assert payload["sub"] == str(user_id)

        response_body = {
            "id": str(run_id),
            "session_id": str(session_id),
            "status": "queued",
            "prompt": "Test prompt",
            "created_at": "2026-08-23T15:00:00Z",
            "timeout_seconds": 60.0,
            "max_steps": 10,
            "answer": None,
            "citations": [],
            "error_code": None,
            "error_message": None,
            "step_count": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "started_at": None,
            "finished_at": None,
        }
        return httpx.Response(status_code=202, json=response_body)

    transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=transport)
    client = AgentServiceClient(
        base_url="http://agent-service.test",
        client=http_client,
    )

    response = client.dispatch_run(
        user_id=user_id,
        prompt="Test prompt",
        session_id=session_id,
    )

    assert isinstance(response, AgentServiceRunResponse)
    assert response.id == run_id
    assert response.session_id == session_id
    assert response.status == "queued"


def test_client_dispatch_passes_delegated_token_header() -> None:
    """When a delegated_token is provided, it is passed in X-Delegated-Token."""
    user_id = uuid.uuid4()
    delegated_token = "sample.delegated.token"

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-Delegated-Token") == delegated_token
        return httpx.Response(
            status_code=202,
            json={
                "id": str(uuid.uuid4()),
                "session_id": str(uuid.uuid4()),
                "status": "queued",
                "prompt": "Prompt",
                "created_at": "2026-08-23T15:00:00Z",
            },
        )

    transport = httpx.MockTransport(mock_handler)
    client = AgentServiceClient(
        base_url="http://agent-service.test",
        client=httpx.Client(transport=transport),
    )

    client.dispatch_run(
        user_id=user_id,
        prompt="Prompt",
        delegated_token=delegated_token,
    )


def test_client_get_run_status() -> None:
    """AgentServiceClient retrieves run snapshot status."""
    run_id = uuid.uuid4()
    session_id = uuid.uuid4()
    user_id = uuid.uuid4()

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == f"/api/v1/runs/{run_id}"
        return httpx.Response(
            status_code=200,
            json={
                "id": str(run_id),
                "session_id": str(session_id),
                "status": "completed",
                "prompt": "Explain photosynthesis.",
                "created_at": "2026-08-23T15:00:00Z",
                "answer": "Photosynthesis is the process...",
                "citations": [],
                "step_count": 2,
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
            },
        )

    transport = httpx.MockTransport(mock_handler)
    client = AgentServiceClient(
        base_url="http://agent-service.test",
        client=httpx.Client(transport=transport),
    )

    result = client.get_run_status(user_id=user_id, run_id=run_id)
    assert result.id == run_id
    assert result.status == "completed"
    assert result.answer == "Photosynthesis is the process..."
    assert result.total_tokens == 150


def test_client_cancel_run() -> None:
    """AgentServiceClient forwards cancellation to Agent Service."""
    run_id = uuid.uuid4()
    user_id = uuid.uuid4()

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/api/v1/runs/{run_id}/cancel"
        return httpx.Response(
            status_code=200,
            json={
                "id": str(run_id),
                "status": "cancelled",
                "detail": "Run cancellation requested.",
            },
        )

    transport = httpx.MockTransport(mock_handler)
    client = AgentServiceClient(
        base_url="http://agent-service.test",
        client=httpx.Client(transport=transport),
    )

    result = client.cancel_run(user_id=user_id, run_id=run_id)
    assert isinstance(result, AgentServiceCancelResponse)
    assert result.id == run_id
    assert result.status == "cancelled"


def test_client_connection_error() -> None:
    """Network connection failure raises AgentServiceConnectionError."""

    def mock_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    transport = httpx.MockTransport(mock_handler)
    client = AgentServiceClient(
        base_url="http://dead-agent-service.test",
        client=httpx.Client(transport=transport),
    )

    with pytest.raises(AgentServiceConnectionError) as exc_info:
        client.dispatch_run(user_id=uuid.uuid4(), prompt="Test")
    assert "Failed to connect to Agent Service" in str(exc_info.value)


def test_client_timeout_error() -> None:
    """Request timeout raises AgentServiceTimeoutError."""

    def mock_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Request timed out after 30s")

    transport = httpx.MockTransport(mock_handler)
    client = AgentServiceClient(
        base_url="http://slow-agent-service.test",
        client=httpx.Client(transport=transport),
    )

    with pytest.raises(AgentServiceTimeoutError) as exc_info:
        client.dispatch_run(user_id=uuid.uuid4(), prompt="Test")
    assert "timed out" in str(exc_info.value)


def test_client_4xx_response_error() -> None:
    """HTTP 400 response raises AgentServiceResponseError."""

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=400,
            json={"detail": "Prompt length cannot be empty."},
        )

    transport = httpx.MockTransport(mock_handler)
    client = AgentServiceClient(
        base_url="http://agent-service.test",
        client=httpx.Client(transport=transport),
    )

    with pytest.raises(AgentServiceResponseError) as exc_info:
        client.dispatch_run(user_id=uuid.uuid4(), prompt="Test")
    assert exc_info.value.status_code == 400
    assert "Prompt length cannot be empty" in exc_info.value.detail


def test_client_5xx_response_error() -> None:
    """HTTP 500 response raises AgentServiceResponseError."""

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=500,
            json={"detail": "Internal server error occurred."},
        )

    transport = httpx.MockTransport(mock_handler)
    client = AgentServiceClient(
        base_url="http://agent-service.test",
        client=httpx.Client(transport=transport),
    )

    with pytest.raises(AgentServiceResponseError) as exc_info:
        client.dispatch_run(user_id=uuid.uuid4(), prompt="Test")
    assert exc_info.value.status_code == 500


def test_client_malformed_response_json() -> None:
    """Non-JSON response raises AgentServiceValidationError."""

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=202,
            content=b"Not JSON at all",
            headers={"Content-Type": "text/plain"},
        )

    transport = httpx.MockTransport(mock_handler)
    client = AgentServiceClient(
        base_url="http://agent-service.test",
        client=httpx.Client(transport=transport),
    )

    with pytest.raises(AgentServiceValidationError) as exc_info:
        client.dispatch_run(user_id=uuid.uuid4(), prompt="Test")
    assert "not valid JSON" in str(exc_info.value)


def test_client_secret_non_leakage_in_exceptions() -> None:
    """Exception strings and representations never expose JWT secrets or tokens."""
    token = mint_platform_execution_jwt(user_id=uuid.uuid4())

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=401,
            json={"detail": "Invalid token."},
        )

    transport = httpx.MockTransport(mock_handler)
    client = AgentServiceClient(
        base_url="http://agent-service.test",
        client=httpx.Client(transport=transport),
    )

    with pytest.raises(AgentServiceResponseError) as exc_info:
        client.dispatch_run(user_id=uuid.uuid4(), prompt="Test")

    error_str = str(exc_info.value)
    assert token not in error_str
    assert settings.SECRET_KEY not in error_str
    assert "mwalimu-insecure-dev-secret-key" not in error_str
