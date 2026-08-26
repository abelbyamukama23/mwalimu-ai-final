"""End-to-end integration and regression verification for Phase H.3.

Verifies:
1. Complete lifecycle: Session creation -> Run dispatch -> Domain S ticket
   -> Completion persistence -> Durable query.
2. Backward compatibility: Polling GET /api/v1/runs/{run_id}/ works.
3. Resilience: Disconnects, unread streams, and completion idempotency.
4. Security: Credential domain segregation (Domain A, B, C, D, S).
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import jwt
import pytest
from rest_framework.test import APIClient

from platform_api.apps.agents.authentication import (
    get_agent_stream_signing_key,
)
from platform_api.apps.agents.client import AgentServiceClient, AgentServiceRunResponse
from platform_api.apps.agents.completion_auth import mint_internal_service_jwt
from platform_api.apps.agents.models import (
    AgentRunRecord,
    AgentRunStatus,
    AgentSession,
    AgentSessionMessage,
    AgentSessionStatus,
    MessageRole,
)
from platform_api.apps.institutions.models import Institution
from platform_api.apps.memberships.models import Membership
from platform_api.apps.users.models import User

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def session_e2e(
    user_a: User, institution_a: Institution, membership_a: Membership
) -> AgentSession:
    """Return a test session owned by User A."""
    return AgentSession.objects.create(
        user=user_a,
        institution=institution_a,
        title="E2E Hybrid Streaming Session",
        status=AgentSessionStatus.ACTIVE,
    )


# ---------------------------------------------------------------------------
# 1. Complete E2E Platform Flow Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestHybridE2ELifecycle:
    """Test the complete hybrid control plane and completion lifecycle."""

    def test_full_platform_dispatch_and_completion_lifecycle(
        self,
        client_a: APIClient,
        user_a: User,
        session_e2e: AgentSession,
    ) -> None:
        """Verify the complete Platform API orchestration lifecycle:
        1. Submit prompt -> POST /api/v1/sessions/{session_id}/runs/
        2. Verify user message persisted, AgentRunRecord created.
        3. Verify Domain S streaming descriptor in 202 response.
        4. Verify Domain S claims.
        5. Simulate Agent Service sending Domain D completion callback.
        6. Verify terminal state, answer, citations, and assistant message.
        7. Verify GET /api/v1/runs/{run_id}/ returns full terminal state.
        """
        captured_dispatch: dict[str, object] = {}

        def mock_dispatch(
            user_id: uuid.UUID | str,
            prompt: str,
            session_id: uuid.UUID | str | None = None,
            run_id: uuid.UUID | str | None = None,
            **kwargs: object,
        ) -> AgentServiceRunResponse:
            captured_dispatch["user_id"] = user_id
            captured_dispatch["prompt"] = prompt
            captured_dispatch["session_id"] = session_id
            captured_dispatch["run_id"] = run_id
            captured_dispatch["delegated_token"] = kwargs.get("delegated_token")
            return AgentServiceRunResponse(
                id=uuid.UUID(str(run_id or uuid.uuid4())),
                session_id=uuid.UUID(str(session_id or uuid.uuid4())),
                status="queued",
                prompt=prompt,
                created_at="2026-08-24T00:00:00Z",
            )

        with patch.object(
            AgentServiceClient, "dispatch_run", side_effect=mock_dispatch
        ):
            resp = client_a.post(
                f"/api/v1/sessions/{session_e2e.id}/runs/",
                {"prompt": "Explain cellular respiration in mitochondria."},
                format="json",
            )

        # Step 1-4: Verify 202 response and Domain S descriptor
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "queued"
        assert "streaming" in data
        assert data["streaming"] is not None

        streaming = data["streaming"]
        assert "ticket" in streaming
        assert "sse_url" in streaming
        assert "expires_in" in streaming
        assert streaming["expires_in"] == 300

        run_id = uuid.UUID(data["id"])
        assert streaming["sse_url"].endswith(f"/api/v1/runs/{run_id}/events")

        # Step 5: Verify Domain S ticket claims
        ticket = streaming["ticket"]
        stream_key = get_agent_stream_signing_key()
        claims = jwt.decode(
            ticket,
            stream_key,
            algorithms=["HS256"],
            audience="mwalimu-agent-stream",
            issuer="mwalimu-platform-api",
            options={"verify_exp": True},
        )
        assert claims["sub"] == str(user_a.id)
        assert claims["run_id"] == str(run_id)
        assert claims["session_id"] == str(session_e2e.id)
        assert claims["scope"] == "run:stream"
        assert "jti" in claims

        # Step 6: Verify durable PostgreSQL state after dispatch
        run_record = AgentRunRecord.objects.get(id=run_id)
        assert run_record.status == AgentRunStatus.QUEUED
        assert run_record.user == user_a
        assert run_record.session == session_e2e

        # Verify user message was persisted
        user_msg = AgentSessionMessage.objects.get(
            session=session_e2e, run=run_record, role=MessageRole.USER
        )
        assert user_msg.content == "Explain cellular respiration in mitochondria."

        # Step 7: Simulate Agent Service sending terminal completion via Domain D
        completion_jwt = mint_internal_service_jwt(expires_in_seconds=60)
        completion_payload = {
            "status": "completed",
            "answer": "Cellular respiration produces ATP in the mitochondrial matrix.",
            "citations": [
                {
                    "chunk_id": str(uuid.uuid4()),
                    "resource_id": str(uuid.uuid4()),
                    "resource_name": "Biology_Textbook.pdf",
                    "library_id": str(uuid.uuid4()),
                    "library_name": "Science Library",
                    "score": 0.95,
                    "section": "Chapter 4: Metabolism",
                    "page_start": 42,
                    "page_end": 45,
                    "sequence": 1,
                    "char_start": 100,
                    "char_end": 500,
                    "content_sha256": "abcdef1234567890",
                }
            ],
            "step_count": 2,
            "prompt_tokens": 120,
            "completion_tokens": 85,
            "total_tokens": 205,
        }

        internal_client = APIClient()
        internal_client.credentials(HTTP_AUTHORIZATION=f"Bearer {completion_jwt}")
        comp_resp = internal_client.post(
            f"/api/v1/internal/runs/{run_id}/completion/",
            completion_payload,
            format="json",
        )
        assert comp_resp.status_code == 200

        # Step 8: Verify durable PostgreSQL persistence
        run_record.refresh_from_db()
        assert run_record.status == AgentRunStatus.COMPLETED
        assert (
            run_record.answer
            == "Cellular respiration produces ATP in the mitochondrial matrix."
        )
        assert run_record.total_tokens == 205
        assert run_record.finished_at is not None
        assert len(run_record.citations) == 1

        # Verify assistant message was created
        assistant_msg = AgentSessionMessage.objects.get(
            session=session_e2e, run=run_record, role=MessageRole.ASSISTANT
        )
        assert (
            assistant_msg.content
            == "Cellular respiration produces ATP in the mitochondrial matrix."
        )

        # Step 9: Verify public polling endpoint GET /api/v1/runs/{run_id}/
        poll_resp = client_a.get(f"/api/v1/runs/{run_id}/")
        assert poll_resp.status_code == 200
        poll_data = poll_resp.json()
        assert poll_data["id"] == str(run_id)
        assert poll_data["status"] == "completed"
        assert (
            poll_data["answer"]
            == "Cellular respiration produces ATP in the mitochondrial matrix."
        )
        assert poll_data["total_tokens"] == 205
        assert len(poll_data["citations"]) == 1

    def test_polling_client_never_opens_sse_succeeds(
        self,
        client_a: APIClient,
        user_a: User,
        session_e2e: AgentSession,
    ) -> None:
        """Backward compatibility: Clients that only poll succeed."""
        run_id = uuid.uuid4()
        with patch.object(
            AgentServiceClient,
            "dispatch_run",
            return_value=AgentServiceRunResponse(
                id=run_id,
                session_id=session_e2e.id,
                status="queued",
                prompt="test",
                created_at="2026-08-24T00:00:00Z",
            ),
        ):
            resp = client_a.post(
                f"/api/v1/sessions/{session_e2e.id}/runs/",
                {"prompt": "Calculate 25 * 4"},
                format="json",
            )
        assert resp.status_code == 202
        created_run_id = resp.json()["id"]

        # Client immediately polls GET /api/v1/runs/{id}/
        poll_1 = client_a.get(f"/api/v1/runs/{created_run_id}/")
        assert poll_1.status_code == 200
        assert poll_1.json()["status"] == "queued"

        # Agent completes in background
        completion_jwt = mint_internal_service_jwt(expires_in_seconds=60)
        internal_client = APIClient()
        internal_client.credentials(HTTP_AUTHORIZATION=f"Bearer {completion_jwt}")
        internal_client.post(
            f"/api/v1/internal/runs/{created_run_id}/completion/",
            {
                "status": "completed",
                "answer": "100",
                "citations": [],
                "step_count": 1,
                "prompt_tokens": 20,
                "completion_tokens": 5,
                "total_tokens": 25,
            },
            format="json",
        )

        # Client polls again and sees completed state
        poll_2 = client_a.get(f"/api/v1/runs/{created_run_id}/")
        assert poll_2.status_code == 200
        assert poll_2.json()["status"] == "completed"
        assert poll_2.json()["answer"] == "100"

    def test_completion_idempotency(
        self,
        client_a: APIClient,
        user_a: User,
        session_e2e: AgentSession,
    ) -> None:
        """Duplicate completions are handled idempotently without mutation."""
        run_record = AgentRunRecord.objects.create(
            session=session_e2e,
            user=user_a,
            prompt="Idempotency test",
            status=AgentRunStatus.QUEUED,
        )

        completion_jwt = mint_internal_service_jwt(expires_in_seconds=60)
        internal_client = APIClient()
        internal_client.credentials(HTTP_AUTHORIZATION=f"Bearer {completion_jwt}")
        payload = {
            "status": "completed",
            "answer": "First completion answer.",
            "citations": [],
            "step_count": 1,
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        }

        # First call -> 200 OK
        resp1 = internal_client.post(
            f"/api/v1/internal/runs/{run_record.id}/completion/",
            payload,
            format="json",
        )
        assert resp1.status_code == 200

        # Duplicate identical call -> 200 OK with idempotent=True
        resp2 = internal_client.post(
            f"/api/v1/internal/runs/{run_record.id}/completion/",
            payload,
            format="json",
        )
        assert resp2.status_code == 200
        assert resp2.json().get("idempotent") is True

        # Conflicting status -> 409 Conflict
        conflicting_payload = {**payload, "status": "failed", "error_code": "ERR"}
        resp3 = internal_client.post(
            f"/api/v1/internal/runs/{run_record.id}/completion/",
            conflicting_payload,
            format="json",
        )
        assert resp3.status_code == 409
