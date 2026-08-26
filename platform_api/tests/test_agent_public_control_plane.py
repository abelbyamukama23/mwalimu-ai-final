"""Tests for the public Platform API control plane (Sessions & Runs)."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import httpx
import pytest
from rest_framework.test import APIClient

from platform_api.apps.agents.client import (
    AgentServiceCancelResponse,
    AgentServiceClient,
    AgentServiceRunResponse,
)
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
from platform_api.apps.libraries.models import (
    Library,
    LibraryAccessPolicy,
    LibraryAccessRole,
)
from platform_api.apps.memberships.models import Membership
from platform_api.apps.users.models import User

# ---------------------------------------------------------------------------
# Test Helpers & Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def session_a(
    user_a: User, institution_a: Institution, membership_a: Membership
) -> AgentSession:
    """Return a test session owned by User A."""
    return AgentSession.objects.create(
        user=user_a,
        institution=institution_a,
        title="Session A",
        status=AgentSessionStatus.ACTIVE,
    )


@pytest.fixture
def session_b(
    user_b: User, institution_b: Institution, membership_b: Membership
) -> AgentSession:
    """Return a test session owned by User B."""
    return AgentSession.objects.create(
        user=user_b,
        institution=institution_b,
        title="Session B",
        status=AgentSessionStatus.ACTIVE,
    )


@pytest.fixture
def run_a(session_a: AgentSession, user_a: User) -> AgentRunRecord:
    """Return a test run record owned by User A."""
    return AgentRunRecord.objects.create(
        session=session_a,
        user=user_a,
        prompt="Initial question",
        status=AgentRunStatus.QUEUED,
    )


def _mock_dispatch_success(prompt: str = "Test") -> AgentServiceRunResponse:
    """Return a canned successful dispatch response."""
    return AgentServiceRunResponse(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        status="queued",
        prompt=prompt,
        created_at="2026-08-23T15:00:00Z",
    )


# ---------------------------------------------------------------------------
# 1. Session Endpoint Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_authenticated_session_creation(
    client_a: APIClient,
    user_a: User,
    institution_a: Institution,
    membership_a: Membership,
) -> None:
    """Authenticated user creates an AgentSession with resolved institution."""
    payload = {"title": "Biology Study Session"}
    response = client_a.post("/api/v1/sessions/", payload, format="json")

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Biology Study Session"
    assert data["institution_id"] == str(institution_a.id)
    assert data["status"] == "active"
    assert "id" in data

    # Verify persistent state
    session = AgentSession.objects.get(id=data["id"])
    assert session.user == user_a
    assert session.institution == institution_a


@pytest.mark.django_db
def test_unauthenticated_session_creation_rejected(api_client: APIClient) -> None:
    """Unauthenticated requests to POST /api/v1/sessions/ return 401 Unauthorized."""
    response = api_client.post("/api/v1/sessions/", {"title": "No Auth"}, format="json")
    assert response.status_code == 401


@pytest.mark.django_db
def test_institution_authorization_verified(
    client_a: APIClient,
    institution_b: Institution,
    membership_a: Membership,
) -> None:
    """User cannot create a session bound to an institution they do not belong to."""
    payload = {
        "title": "Unauthorized Institution Session",
        "institution_id": str(institution_b.id),
    }
    response = client_a.post("/api/v1/sessions/", payload, format="json")
    assert response.status_code == 400
    assert "institution_id" in response.json()


@pytest.mark.django_db
def test_primary_library_authorization_accessible(
    client_a: APIClient,
    user_a: User,
    institution_a: Institution,
    library_a: Library,
    membership_a: Membership,
) -> None:
    """User with access policy can bind session to primary_library."""
    LibraryAccessPolicy.objects.create(
        user=user_a,
        library=library_a,
        role=LibraryAccessRole.STUDENT,
    )
    payload = {
        "title": "Genetics Session",
        "institution_id": str(institution_a.id),
        "primary_library_id": str(library_a.id),
    }
    response = client_a.post("/api/v1/sessions/", payload, format="json")
    assert response.status_code == 201
    assert response.json()["primary_library_id"] == str(library_a.id)


@pytest.mark.django_db
def test_unauthorized_library_rejected(
    client_a: APIClient,
    institution_a: Institution,
    library_b: Library,
    membership_a: Membership,
) -> None:
    """Binding session to foreign or unauthorized library is rejected with 400."""
    payload = {
        "title": "Cross Institution Library Session",
        "institution_id": str(institution_a.id),
        "primary_library_id": str(library_b.id),
    }
    response = client_a.post("/api/v1/sessions/", payload, format="json")
    assert response.status_code == 400
    assert "primary_library_id" in response.json()


@pytest.mark.django_db
def test_session_listing_isolation(
    client_a: APIClient,
    client_b: APIClient,
    session_a: AgentSession,
    session_b: AgentSession,
) -> None:
    """Users only see their own sessions in GET /api/v1/sessions/."""
    res_a = client_a.get("/api/v1/sessions/")
    assert res_a.status_code == 200
    results_a = res_a.json().get("results", res_a.json())
    ids_a = [s["id"] for s in results_a]
    assert str(session_a.id) in ids_a
    assert str(session_b.id) not in ids_a

    res_b = client_b.get("/api/v1/sessions/")
    assert res_b.status_code == 200
    results_b = res_b.json().get("results", res_b.json())
    ids_b = [s["id"] for s in results_b]
    assert str(session_b.id) in ids_b
    assert str(session_a.id) not in ids_b


@pytest.mark.django_db
def test_session_detail_isolation(
    client_a: APIClient,
    client_b: APIClient,
    session_a: AgentSession,
) -> None:
    """User B cannot retrieve User A's session detail (returns 404 Not Found)."""
    res_owner = client_a.get(f"/api/v1/sessions/{session_a.id}/")
    assert res_owner.status_code == 200
    assert res_owner.json()["id"] == str(session_a.id)

    res_foreign = client_b.get(f"/api/v1/sessions/{session_a.id}/")
    assert res_foreign.status_code == 404


@pytest.mark.django_db
def test_transcript_ordering_sequence_asc(
    client_a: APIClient,
    session_a: AgentSession,
) -> None:
    """Transcript messages in session detail are ordered strictly by sequence ASC."""
    AgentSessionMessage.objects.create(
        session=session_a,
        role=MessageRole.USER,
        content="First question",
        sequence=0,
    )
    AgentSessionMessage.objects.create(
        session=session_a,
        role=MessageRole.ASSISTANT,
        content="First answer",
        sequence=1,
    )
    AgentSessionMessage.objects.create(
        session=session_a,
        role=MessageRole.USER,
        content="Second question",
        sequence=2,
    )

    response = client_a.get(f"/api/v1/sessions/{session_a.id}/")
    assert response.status_code == 200
    messages = response.json()["messages"]
    assert len(messages) == 3
    assert [m["sequence"] for m in messages] == [0, 1, 2]
    assert messages[0]["content"] == "First question"
    assert messages[1]["content"] == "First answer"
    assert messages[2]["content"] == "Second question"


# ---------------------------------------------------------------------------
# 2. Run Creation Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_valid_run_creation(
    client_a: APIClient,
    session_a: AgentSession,
) -> None:
    """Submitting valid prompt creates run, user message, and returns 202 Accepted."""
    payload = {
        "prompt": "What is photosynthesis?",
        "max_steps": 5,
        "timeout_seconds": 30.0,
        "token_budget": 2000,
        "locale": "en",
        "tool_allowlist": ["calculator", "knowledge_search"],
    }

    with patch.object(
        AgentServiceClient,
        "dispatch_run",
        return_value=_mock_dispatch_success("What is photosynthesis?"),
    ):
        response = client_a.post(
            f"/api/v1/sessions/{session_a.id}/runs/",
            payload,
            format="json",
        )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "queued"
    assert data["prompt"] == "What is photosynthesis?"
    assert data["max_steps"] == 5
    assert data["timeout_seconds"] == 30.0
    assert data["session_id"] == str(session_a.id)

    # Verify user message was persisted in PostgreSQL
    user_msg = AgentSessionMessage.objects.filter(
        session=session_a, role=MessageRole.USER
    ).first()
    assert user_msg is not None
    assert user_msg.content == "What is photosynthesis?"
    assert user_msg.sequence == 0


@pytest.mark.django_db
def test_invalid_prompt_rejected(
    client_a: APIClient,
    session_a: AgentSession,
) -> None:
    """Empty or missing prompt is rejected with 400 Bad Request."""
    response = client_a.post(
        f"/api/v1/sessions/{session_a.id}/runs/",
        {"prompt": ""},
        format="json",
    )
    assert response.status_code == 400
    assert "prompt" in response.json()


@pytest.mark.django_db
def test_invalid_max_steps_rejected(
    client_a: APIClient,
    session_a: AgentSession,
) -> None:
    """Out-of-bounds max_steps (<1 or >50) is rejected with 400."""
    res_zero = client_a.post(
        f"/api/v1/sessions/{session_a.id}/runs/",
        {"prompt": "Hello", "max_steps": 0},
        format="json",
    )
    assert res_zero.status_code == 400

    res_huge = client_a.post(
        f"/api/v1/sessions/{session_a.id}/runs/",
        {"prompt": "Hello", "max_steps": 100},
        format="json",
    )
    assert res_huge.status_code == 400


@pytest.mark.django_db
def test_invalid_timeout_rejected(
    client_a: APIClient,
    session_a: AgentSession,
) -> None:
    """Out-of-bounds timeout (<1.0 or >300.0) is rejected with 400."""
    res_low = client_a.post(
        f"/api/v1/sessions/{session_a.id}/runs/",
        {"prompt": "Hello", "timeout_seconds": 0.5},
        format="json",
    )
    assert res_low.status_code == 400

    res_high = client_a.post(
        f"/api/v1/sessions/{session_a.id}/runs/",
        {"prompt": "Hello", "timeout_seconds": 500.0},
        format="json",
    )
    assert res_high.status_code == 400


@pytest.mark.django_db
def test_invalid_token_budget_rejected(
    client_a: APIClient,
    session_a: AgentSession,
) -> None:
    """Out-of-bounds token budget (<100 or >32000) is rejected with 400."""
    res = client_a.post(
        f"/api/v1/sessions/{session_a.id}/runs/",
        {"prompt": "Hello", "token_budget": 50},
        format="json",
    )
    assert res.status_code == 400


@pytest.mark.django_db
def test_invalid_tool_allowlist_rejected(
    client_a: APIClient,
    session_a: AgentSession,
) -> None:
    """Unrecognized tool in tool_allowlist is rejected with 400."""
    res = client_a.post(
        f"/api/v1/sessions/{session_a.id}/runs/",
        {
            "prompt": "Hello",
            "tool_allowlist": ["calculator", "unauthorized_admin_tool"],
        },
        format="json",
    )
    assert res.status_code == 400
    assert "tool_allowlist" in res.json()


@pytest.mark.django_db
def test_unauthorized_session_run_creation_rejected(
    client_b: APIClient,
    session_a: AgentSession,
) -> None:
    """User B cannot create a run in User A's session (returns 404 Not Found)."""
    response = client_b.post(
        f"/api/v1/sessions/{session_a.id}/runs/",
        {"prompt": "Hijack attempt"},
        format="json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_capability_narrowing_valid_subset(
    client_a: APIClient,
    session_a: AgentSession,
) -> None:
    """Client can restrict capabilities to a subset of authorized tools."""
    with patch.object(
        AgentServiceClient,
        "dispatch_run",
        return_value=_mock_dispatch_success("Math question"),
    ) as mock_dispatch:
        response = client_a.post(
            f"/api/v1/sessions/{session_a.id}/runs/",
            {"prompt": "Math question", "tool_allowlist": ["calculator"]},
            format="json",
        )
    assert response.status_code == 202
    mock_dispatch.assert_called_once()
    assert mock_dispatch.call_args.kwargs["tool_allowlist"] == ["calculator"]


@pytest.mark.django_db
def test_no_credential_acceptance_in_run_creation(
    client_a: APIClient,
    session_a: AgentSession,
    user_b: User,
) -> None:
    """Passing credentials or user_id does not override server authority."""
    payload = {
        "prompt": "Secure prompt",
        "user_id": str(user_b.id),
        "delegated_token": "fake-token",
        "system_prompt": "Override instructions",
    }
    with patch.object(
        AgentServiceClient,
        "dispatch_run",
        return_value=_mock_dispatch_success("Secure prompt"),
    ) as mock_dispatch:
        response = client_a.post(
            f"/api/v1/sessions/{session_a.id}/runs/",
            payload,
            format="json",
        )
    assert response.status_code == 202
    # Ensure dispatch used authenticated caller's identity (user_a)
    assert mock_dispatch.call_args.kwargs["user_id"] == session_a.user.pk


# ---------------------------------------------------------------------------
# 3. Run Status & Snapshot Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_owner_can_retrieve_run_status(
    client_a: APIClient,
    run_a: AgentRunRecord,
) -> None:
    """Owner can retrieve durable run status via GET /api/v1/runs/{id}/."""
    response = client_a.get(f"/api/v1/runs/{run_a.id}/")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(run_a.id)
    assert data["status"] == "queued"
    assert data["prompt"] == "Initial question"


@pytest.mark.django_db
def test_foreign_user_cannot_retrieve_run_status(
    client_b: APIClient,
    run_a: AgentRunRecord,
) -> None:
    """User B cannot retrieve User A's run status (returns 404 Not Found)."""
    response = client_b.get(f"/api/v1/runs/{run_a.id}/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_run_status_reads_from_postgres(
    client_a: APIClient,
    run_a: AgentRunRecord,
) -> None:
    """GET /api/v1/runs/{id}/ reads durable state without network calls."""
    run_a.status = AgentRunStatus.RUNNING
    run_a.step_count = 3
    run_a.save()

    response = client_a.get(f"/api/v1/runs/{run_a.id}/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert data["step_count"] == 3


@pytest.mark.django_db
def test_agent_service_unavailable_does_not_prevent_status_retrieval(
    client_a: APIClient,
    run_a: AgentRunRecord,
) -> None:
    """Status query succeeds even when Agent Service is offline/unreachable."""
    with patch(
        "httpx.Client.get",
        side_effect=httpx.ConnectError("Connection refused"),
    ):
        response = client_a.get(f"/api/v1/runs/{run_a.id}/")
    assert response.status_code == 200
    assert response.json()["id"] == str(run_a.id)


# ---------------------------------------------------------------------------
# 4. Cancellation Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_owner_can_cancel_run(
    client_a: APIClient,
    run_a: AgentRunRecord,
) -> None:
    """Owner can cancel an active run; updates durable status to CANCELLED."""
    with patch.object(
        AgentServiceClient,
        "cancel_run",
        return_value=AgentServiceCancelResponse(
            id=run_a.id, status="cancelled", detail="Cancelled."
        ),
    ):
        response = client_a.post(f"/api/v1/runs/{run_a.id}/cancel/")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cancelled"
    assert data["error_code"] == "CANCELLED"

    run_a.refresh_from_db()
    assert run_a.status == AgentRunStatus.CANCELLED
    assert run_a.finished_at is not None


@pytest.mark.django_db
def test_foreign_user_cannot_cancel_run(
    client_b: APIClient,
    run_a: AgentRunRecord,
) -> None:
    """User B cannot cancel User A's run (returns 404 Not Found)."""
    response = client_b.post(f"/api/v1/runs/{run_a.id}/cancel/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_duplicate_cancellation_is_idempotent(
    client_a: APIClient,
    run_a: AgentRunRecord,
) -> None:
    """Repeated cancellation of an already-cancelled run succeeds idempotently."""
    run_a.status = AgentRunStatus.CANCELLED
    run_a.error_code = "CANCELLED"
    run_a.save()

    response = client_a.post(f"/api/v1/runs/{run_a.id}/cancel/")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


@pytest.mark.django_db
def test_completed_run_cannot_be_resurrected_by_cancel(
    client_a: APIClient,
    run_a: AgentRunRecord,
) -> None:
    """Cancelling an already-COMPLETED run does not mutate its terminal status."""
    run_a.status = AgentRunStatus.COMPLETED
    run_a.answer = "Synthesized answer."
    run_a.save()

    response = client_a.post(f"/api/v1/runs/{run_a.id}/cancel/")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"

    run_a.refresh_from_db()
    assert run_a.status == AgentRunStatus.COMPLETED
    assert run_a.answer == "Synthesized answer."


@pytest.mark.django_db
def test_timed_out_run_cannot_be_resurrected_by_cancel(
    client_a: APIClient,
    run_a: AgentRunRecord,
) -> None:
    """Cancelling an already-TIMED_OUT run does not mutate its terminal status."""
    run_a.status = AgentRunStatus.TIMED_OUT
    run_a.error_code = "TIMEOUT"
    run_a.save()

    response = client_a.post(f"/api/v1/runs/{run_a.id}/cancel/")
    assert response.status_code == 200
    assert response.json()["status"] == "timed_out"

    run_a.refresh_from_db()
    assert run_a.status == AgentRunStatus.TIMED_OUT


@pytest.mark.django_db
def test_agent_service_unavailable_does_not_corrupt_cancellation(
    client_a: APIClient,
    run_a: AgentRunRecord,
) -> None:
    """Run is successfully marked CANCELLED locally even if Agent Service is offline."""
    with patch(
        "httpx.Client.post",
        side_effect=httpx.ConnectError("Connection refused"),
    ):
        response = client_a.post(f"/api/v1/runs/{run_a.id}/cancel/")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    run_a.refresh_from_db()
    assert run_a.status == AgentRunStatus.CANCELLED


@pytest.mark.django_db
def test_stale_completion_cannot_resurrect_cancelled_run(
    client_a: APIClient,
    api_client: APIClient,
    run_a: AgentRunRecord,
    session_a: AgentSession,
) -> None:
    """Stale completion callback on cancelled run returns 409 Conflict."""
    # User cancels run
    client_a.post(f"/api/v1/runs/{run_a.id}/cancel/")
    run_a.refresh_from_db()
    assert run_a.status == AgentRunStatus.CANCELLED

    # Agent Service asynchronously sends COMPLETED completion callback
    token = mint_internal_service_jwt()
    completion_payload = {
        "status": "completed",
        "answer": "Late answer",
    }
    url = f"/api/v1/internal/runs/{run_a.id}/completion/"
    res = api_client.post(
        url,
        completion_payload,
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert res.status_code == 409
    assert res.json()["error_code"] == "CONFLICTING_TERMINAL_STATE"

    # Confirm no assistant message was inserted
    assert (
        AgentSessionMessage.objects.filter(
            session=session_a, role=MessageRole.ASSISTANT
        ).count()
        == 0
    )


# ---------------------------------------------------------------------------
# 5. Multi-Turn Transcript Synchronization Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_multi_turn_transcript_flow(
    client_a: APIClient,
    api_client: APIClient,
    session_a: AgentSession,
) -> None:
    """Full multi-turn lifecycle: user prompt -> run -> completion -> transcript."""
    token = mint_internal_service_jwt()

    # Turn 1: Dispatch Prompt 1
    with patch.object(
        AgentServiceClient,
        "dispatch_run",
        return_value=_mock_dispatch_success("What is 2+2?"),
    ):
        res1 = client_a.post(
            f"/api/v1/sessions/{session_a.id}/runs/",
            {"prompt": "What is 2+2?"},
            format="json",
        )
    assert res1.status_code == 202
    run1_id = res1.json()["id"]

    # Turn 1 Completion: Agent Service completes run 1
    api_client.post(
        f"/api/v1/internal/runs/{run1_id}/completion/",
        {"status": "completed", "answer": "4", "step_count": 1},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    # Turn 2: Dispatch Prompt 2
    with patch.object(
        AgentServiceClient,
        "dispatch_run",
        return_value=_mock_dispatch_success("Multiply that by 10"),
    ) as mock_dispatch2:
        res2 = client_a.post(
            f"/api/v1/sessions/{session_a.id}/runs/",
            {"prompt": "Multiply that by 10"},
            format="json",
        )
    assert res2.status_code == 202
    run2_id = res2.json()["id"]

    # Verify conversation_history passed to Agent Service contains Turn 1 messages
    history = mock_dispatch2.call_args.kwargs["conversation_history"]
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "What is 2+2?"}
    assert history[1] == {"role": "assistant", "content": "4"}

    # Turn 2 Completion
    api_client.post(
        f"/api/v1/internal/runs/{run2_id}/completion/",
        {"status": "completed", "answer": "40", "step_count": 1},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    # Retrieve session detail and verify canonical transcript sequence
    detail_res = client_a.get(f"/api/v1/sessions/{session_a.id}/")
    assert detail_res.status_code == 200
    messages = detail_res.json()["messages"]
    assert len(messages) == 4
    assert [m["sequence"] for m in messages] == [0, 1, 2, 3]
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "What is 2+2?"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "4"
    assert messages[2]["role"] == "user"
    assert messages[2]["content"] == "Multiply that by 10"
    assert messages[3]["role"] == "assistant"
    assert messages[3]["content"] == "40"


# ---------------------------------------------------------------------------
# 6. Security Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_no_user_id_spoofing(
    client_a: APIClient,
    user_b: User,
    membership_a: Membership,
) -> None:
    """User cannot spoof user_id when creating a session."""
    payload = {
        "title": "Spoof Session",
        "user_id": str(user_b.id),
    }
    response = client_a.post("/api/v1/sessions/", payload, format="json")
    assert response.status_code == 201

    session = AgentSession.objects.get(id=response.json()["id"])
    assert session.user != user_b
    assert session.user == membership_a.user


@pytest.mark.django_db
def test_no_credential_leakage_in_responses(
    client_a: APIClient,
    session_a: AgentSession,
    run_a: AgentRunRecord,
) -> None:
    """Public session and run responses contain zero tokens, credentials, or secrets."""
    res_session = client_a.get(f"/api/v1/sessions/{session_a.id}/")
    assert res_session.status_code == 200
    session_str = str(res_session.json())
    assert "token" not in session_str.lower() or "total_tokens" in session_str
    assert "jwt" not in session_str.lower()
    assert "secret" not in session_str.lower()

    res_run = client_a.get(f"/api/v1/runs/{run_a.id}/")
    assert res_run.status_code == 200
    run_str = str(res_run.json())
    assert "jwt" not in run_str.lower()
    assert "secret" not in run_str.lower()
    assert "deepseek" not in run_str.lower()
