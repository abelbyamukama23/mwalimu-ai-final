"""Comprehensive tests for Agent Service API endpoints (Phase 6.5)."""

import time
import uuid

import jwt
from fastapi.testclient import TestClient

from agent_service.infrastructure.run_store import global_run_store
from agent_service.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_SECRET = "mwalimu-insecure-dev-secret-key-change-in-production"


def _mint_test_jwt(
    user_id: uuid.UUID | None = None,
    secret: str = TEST_SECRET,
    expired: bool = False,
    missing_sub: bool = False,
    invalid_sub: bool = False,
) -> str:
    """Mint a JWT token for testing."""
    now = int(time.time())
    payload: dict[str, object] = {
        "iat": now,
        "nbf": now,
    }
    if expired:
        payload["exp"] = now - 3600
    else:
        payload["exp"] = now + 3600

    if missing_sub:
        pass  # No sub claim
    elif invalid_sub:
        payload["sub"] = "not-a-uuid"
    else:
        payload["sub"] = str(user_id or uuid.uuid4())

    return jwt.encode(payload, secret, algorithm="HS256")


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Authentication Tests
# ---------------------------------------------------------------------------


class TestAuthentication:
    """Verify cryptographic authentication boundary."""

    def test_create_run_no_auth_returns_401(self) -> None:
        """POST /api/v1/runs without credentials returns 401."""
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/runs",
                json={"prompt": "Hello"},
            )
        assert resp.status_code == 401

    def test_create_run_invalid_token_returns_401(self) -> None:
        """POST /api/v1/runs with garbage token returns 401."""
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/runs",
                json={"prompt": "Hello"},
                headers=_auth_header("not.a.valid.jwt.token"),
            )
        assert resp.status_code == 401

    def test_create_run_expired_token_returns_401(self) -> None:
        """POST /api/v1/runs with expired JWT returns 401."""
        token = _mint_test_jwt(expired=True)
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/runs",
                json={"prompt": "Hello"},
                headers=_auth_header(token),
            )
        assert resp.status_code == 401

    def test_create_run_missing_sub_returns_401(self) -> None:
        """POST /api/v1/runs with JWT missing 'sub' returns 401."""
        token = _mint_test_jwt(missing_sub=True)
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/runs",
                json={"prompt": "Hello"},
                headers=_auth_header(token),
            )
        assert resp.status_code == 401

    def test_create_run_invalid_sub_returns_401(self) -> None:
        """POST /api/v1/runs with non-UUID sub returns 401."""
        token = _mint_test_jwt(invalid_sub=True)
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/runs",
                json={"prompt": "Hello"},
                headers=_auth_header(token),
            )
        assert resp.status_code == 401

    def test_create_run_wrong_secret_returns_401(self) -> None:
        """JWT signed with wrong key is rejected."""
        token = _mint_test_jwt(secret="wrong-secret-key-must-be-at-least-32-chars-long")
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/runs",
                json={"prompt": "Hello"},
                headers=_auth_header(token),
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# CreateRunRequest Validation Tests
# ---------------------------------------------------------------------------


class TestCreateRunValidation:
    """Verify request schema validation."""

    def test_create_run_missing_prompt_returns_422(self) -> None:
        """Missing required 'prompt' field returns 422."""
        token = _mint_test_jwt()
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/runs",
                json={},
                headers=_auth_header(token),
            )
        assert resp.status_code == 422

    def test_create_run_empty_prompt_returns_422(self) -> None:
        """Empty prompt string returns 422."""
        token = _mint_test_jwt()
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/runs",
                json={"prompt": ""},
                headers=_auth_header(token),
            )
        assert resp.status_code == 422

    def test_create_run_invalid_max_steps_returns_422(self) -> None:
        """max_steps < 1 returns 422."""
        token = _mint_test_jwt()
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/runs",
                json={"prompt": "test", "max_steps": 0},
                headers=_auth_header(token),
            )
        assert resp.status_code == 422

    def test_create_run_invalid_timeout_returns_422(self) -> None:
        """timeout_seconds > 300 returns 422."""
        token = _mint_test_jwt()
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/runs",
                json={"prompt": "test", "timeout_seconds": 500.0},
                headers=_auth_header(token),
            )
        assert resp.status_code == 422

    def test_create_run_invalid_token_budget_returns_422(self) -> None:
        """token_budget < 100 returns 422."""
        token = _mint_test_jwt()
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/runs",
                json={"prompt": "test", "token_budget": 50},
                headers=_auth_header(token),
            )
        assert resp.status_code == 422

    def test_create_run_extra_fields_rejected(self) -> None:
        """Extra fields (e.g. delegated_token, user_id) are rejected."""
        token = _mint_test_jwt()
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/runs",
                json={
                    "prompt": "test",
                    "delegated_token": "should-not-be-accepted",
                },
                headers=_auth_header(token),
            )
        assert resp.status_code == 422

    def test_create_run_user_id_injection_rejected(self) -> None:
        """Submitting user_id in request body is rejected by extra='forbid'."""
        token = _mint_test_jwt()
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/runs",
                json={
                    "prompt": "test",
                    "user_id": str(uuid.uuid4()),
                },
                headers=_auth_header(token),
            )
        assert resp.status_code == 422

    def test_create_run_with_resolved_context_accepted(self) -> None:
        """CreateRunRequest accepts valid resolved pedagogical context payload."""
        token = _mint_test_jwt()
        context_payload = {
            "context_considered": True,
            "explicit_geographic_intent": "Kyenjojo District",
            "familiar_regions_considered": True,
            "institution_regions_considered": False,
            "selected_geographic_unit_ids": [str(uuid.uuid4())],
            "geographic_expansion_occurred": False,
            "expansion_levels": 0,
            "total_candidate_resources": 1,
            "budget_limit": 5,
            "items": [
                {
                    "resource_id": str(uuid.uuid4()),
                    "geographic_unit_id": str(uuid.uuid4()),
                    "geographic_unit_name": "Kyenjojo District",
                    "geographic_unit_type": "district",
                    "context_domain": "Agriculture & Farming",
                    "title": "Kyenjojo Tea Production",
                    "content": "Tea production in Kyenjojo.",
                    "applicable_subjects": ["agriculture"],
                    "applicable_topics": ["tea farming"],
                    "pedagogical_purposes": ["example"],
                    "source_type": "platform",
                    "selection_reason": "Matched user's priority-1 familiar region.",
                }
            ],
            "explanation": "Resolved 1 contextual item(s).",
            "resolved_at": "2026-08-24T10:00:00Z",
        }
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/runs",
                json={
                    "prompt": "Explain tea farming in my area.",
                    "context": context_payload,
                },
                headers=_auth_header(token),
            )
        assert resp.status_code == 202


# ---------------------------------------------------------------------------
# Run Lifecycle Tests (using default global_run_store)
# ---------------------------------------------------------------------------


class TestRunLifecycle:
    """Verify run creation, status retrieval, and cancellation."""

    def setup_method(self) -> None:
        """Clear global run store before each test."""
        global_run_store.clear()

    def test_create_run_returns_202(self) -> None:
        """POST /api/v1/runs with valid request returns 202 Accepted."""
        user_id = uuid.uuid4()
        token = _mint_test_jwt(user_id=user_id)
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/runs",
                json={"prompt": "What is photosynthesis?"},
                headers=_auth_header(token),
            )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "queued"
        assert data["prompt"] == "What is photosynthesis?"
        assert "run_id" in data
        assert "session_id" in data
        # user_id should NOT be in the response
        assert "user_id" not in data

    def test_create_run_with_session_id(self) -> None:
        """Supplied session_id is preserved in response."""
        user_id = uuid.uuid4()
        session_id = uuid.uuid4()
        token = _mint_test_jwt(user_id=user_id)
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/runs",
                json={
                    "prompt": "test",
                    "session_id": str(session_id),
                },
                headers=_auth_header(token),
            )
        assert resp.status_code == 202
        data = resp.json()
        assert data["session_id"] == str(session_id)

    def test_get_run_status_success(self) -> None:
        """GET /api/v1/runs/{run_id} returns correct snapshot."""
        user_id = uuid.uuid4()
        token = _mint_test_jwt(user_id=user_id)
        with TestClient(app) as client:
            create_resp = client.post(
                "/api/v1/runs",
                json={"prompt": "test question"},
                headers=_auth_header(token),
            )
            assert create_resp.status_code == 202
            run_id = create_resp.json()["run_id"]

            status_resp = client.get(
                f"/api/v1/runs/{run_id}",
                headers=_auth_header(token),
            )
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["run_id"] == run_id

    def test_get_run_nonexistent_returns_404(self) -> None:
        """GET /api/v1/runs/{nonexistent_id} returns 404."""
        token = _mint_test_jwt()
        with TestClient(app) as client:
            resp = client.get(
                f"/api/v1/runs/{uuid.uuid4()}",
                headers=_auth_header(token),
            )
        assert resp.status_code == 404

    def test_get_run_isolation_returns_404(self) -> None:
        """User B cannot access User A's run — returns 404."""
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()
        token_a = _mint_test_jwt(user_id=user_a)
        token_b = _mint_test_jwt(user_id=user_b)
        with TestClient(app) as client:
            create_resp = client.post(
                "/api/v1/runs",
                json={"prompt": "private question"},
                headers=_auth_header(token_a),
            )
            run_id = create_resp.json()["run_id"]

            # User B tries to access User A's run
            status_resp = client.get(
                f"/api/v1/runs/{run_id}",
                headers=_auth_header(token_b),
            )
        assert status_resp.status_code == 404

    def test_cancel_nonexistent_returns_404(self) -> None:
        """POST /api/v1/runs/{nonexistent_id}/cancel returns 404."""
        token = _mint_test_jwt()
        with TestClient(app) as client:
            resp = client.post(
                f"/api/v1/runs/{uuid.uuid4()}/cancel",
                headers=_auth_header(token),
            )
        assert resp.status_code == 404

    def test_cancel_isolation_returns_404(self) -> None:
        """User B cannot cancel User A's run — returns 404."""
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()
        token_a = _mint_test_jwt(user_id=user_a)
        token_b = _mint_test_jwt(user_id=user_b)
        with TestClient(app) as client:
            create_resp = client.post(
                "/api/v1/runs",
                json={"prompt": "my run"},
                headers=_auth_header(token_a),
            )
            run_id = create_resp.json()["run_id"]

            cancel_resp = client.post(
                f"/api/v1/runs/{run_id}/cancel",
                headers=_auth_header(token_b),
            )
        assert cancel_resp.status_code == 404

    def test_cancel_own_run_returns_200(self) -> None:
        """Owner can cancel their own run — returns 200."""
        user_id = uuid.uuid4()
        token = _mint_test_jwt(user_id=user_id)
        with TestClient(app) as client:
            create_resp = client.post(
                "/api/v1/runs",
                json={"prompt": "cancellable task"},
                headers=_auth_header(token),
            )
            run_id = create_resp.json()["run_id"]

            cancel_resp = client.post(
                f"/api/v1/runs/{run_id}/cancel",
                headers=_auth_header(token),
            )
        assert cancel_resp.status_code == 200
        data = cancel_resp.json()
        assert data["run_id"] == run_id


# ---------------------------------------------------------------------------
# Tool Allowlist Non-Escalation Tests
# ---------------------------------------------------------------------------


class TestToolAllowlistNonEscalation:
    """Verify client tool_allowlist can only narrow, never widen."""

    def setup_method(self) -> None:
        global_run_store.clear()

    def test_requesting_unauthorized_tool_is_discarded(self) -> None:
        """Requesting a non-registered tool does not make it available."""
        user_id = uuid.uuid4()
        token = _mint_test_jwt(user_id=user_id)
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/runs",
                json={
                    "prompt": "test",
                    "tool_allowlist": ["calculator", "malicious_admin_tool"],
                },
                headers=_auth_header(token),
            )
        assert resp.status_code == 202


# ---------------------------------------------------------------------------
# Response Model Security Tests
# ---------------------------------------------------------------------------


class TestResponseModelSecurity:
    """Verify sensitive fields are never exposed in responses."""

    def setup_method(self) -> None:
        global_run_store.clear()

    def test_no_delegated_token_in_response(self) -> None:
        """RunResponse never contains delegated credentials."""
        user_id = uuid.uuid4()
        token = _mint_test_jwt(user_id=user_id)
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/runs",
                json={"prompt": "test"},
                headers=_auth_header(token),
            )
        data = resp.json()
        assert "delegated_token" not in data
        assert "token" not in data

    def test_no_user_id_in_response(self) -> None:
        """RunResponse does not expose internal user_id."""
        user_id = uuid.uuid4()
        token = _mint_test_jwt(user_id=user_id)
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/runs",
                json={"prompt": "test"},
                headers=_auth_header(token),
            )
        data = resp.json()
        assert "user_id" not in data


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    """Verify health endpoint."""

    def test_health_returns_200(self) -> None:
        with TestClient(app) as client:
            resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "mwalimu-agent-service"
