"""Tests for Platform API internal run completion endpoint."""

from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

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
from platform_api.apps.libraries.models import Library, LibraryVisibility

User = get_user_model()


@pytest.fixture
def institution(db: None) -> Institution:
    """Create a test institution."""
    return Institution.objects.create(
        name="Completion Test Institution",
        slug=f"completion-test-{uuid.uuid4().hex[:8]}",
    )


@pytest.fixture
def user(db: None, institution: Institution) -> User:
    """Create a test user."""
    return User.objects.create_user(
        email=f"completion_user_{uuid.uuid4().hex[:8]}@example.com",
        password="ValidPassword123!",
    )


@pytest.fixture
def library(db: None, institution: Institution, user: User) -> Library:
    """Create a test library."""
    return Library.objects.create(
        institution=institution,
        name="Completion Biology Library",
        slug=f"comp-bio-{uuid.uuid4().hex[:8]}",
        visibility=LibraryVisibility.DISCOVERABLE,
    )


@pytest.fixture
def session(
    db: None, user: User, institution: Institution, library: Library
) -> AgentSession:
    """Create a test agent session."""
    return AgentSession.objects.create(
        user=user,
        institution=institution,
        primary_library=library,
        title="Completion Test Session",
        status=AgentSessionStatus.ACTIVE,
    )


@pytest.fixture
def active_run(db: None, session: AgentSession, user: User) -> AgentRunRecord:
    """Create an active (QUEUED) agent run record."""
    return AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Explain mitochondrial respiration.",
        status=AgentRunStatus.QUEUED,
    )


@pytest.fixture
def api_client() -> APIClient:
    """Create APIClient."""
    return APIClient()


@pytest.fixture
def domain_d_auth_header() -> dict[str, str]:
    """Create Domain D authorization header."""
    token = mint_internal_service_jwt()
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.mark.django_db
def test_successful_completed_run_syncs_and_creates_assistant_message(
    api_client: APIClient,
    active_run: AgentRunRecord,
    session: AgentSession,
    library: Library,
    domain_d_auth_header: dict[str, str],
) -> None:
    """COMPLETED callback updates run record and creates assistant message."""
    # Pre-populate a user message at sequence 0
    AgentSessionMessage.objects.create(
        session=session,
        role=MessageRole.USER,
        content="Explain mitochondrial respiration.",
        sequence=0,
    )

    citation_payload = {
        "resource_id": str(uuid.uuid4()),
        "resource_name": "Cellular Biology Chapter 4",
        "library_id": str(library.id),
        "library_name": library.name,
        "page_start": 45,
        "page_end": 48,
        "section": "Electron Transport Chain",
        "sequence": 1,
        "char_start": 100,
        "char_end": 500,
        "content_sha256": "abc123def456",
        "chunk_id": str(uuid.uuid4()),
        "score": 0.92,
    }

    payload = {
        "status": "completed",
        "answer": (
            "Mitochondrial respiration produces ATP through oxidative phosphorylation."
        ),
        "citations": [citation_payload],
        "step_count": 3,
        "prompt_tokens": 1200,
        "completion_tokens": 350,
        "total_tokens": 1550,
        "started_at": timezone.now().isoformat(),
        "finished_at": timezone.now().isoformat(),
    }

    url = f"/api/v1/internal/runs/{active_run.id}/completion/"
    response = api_client.post(url, payload, format="json", **domain_d_auth_header)

    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == str(active_run.id)
    assert data["status"] == "completed"
    assert data["idempotent"] is False

    # Check updated AgentRunRecord in database
    active_run.refresh_from_db()
    assert active_run.status == AgentRunStatus.COMPLETED
    assert (
        active_run.answer
        == "Mitochondrial respiration produces ATP through oxidative phosphorylation."
    )
    assert active_run.step_count == 3
    assert active_run.prompt_tokens == 1200
    assert active_run.completion_tokens == 350
    assert active_run.total_tokens == 1550
    assert len(active_run.citations) == 1
    assert active_run.citations[0]["resource_name"] == "Cellular Biology Chapter 4"
    assert active_run.finished_at is not None

    # Check created AgentSessionMessage
    assistant_msgs = AgentSessionMessage.objects.filter(
        session=session, role=MessageRole.ASSISTANT
    )
    assert assistant_msgs.count() == 1
    msg = assistant_msgs.first()
    assert msg is not None
    assert msg.run_id == active_run.id
    assert msg.content == active_run.answer
    assert msg.sequence == 1
    assert len(msg.citations) == 1


@pytest.mark.django_db
def test_successful_failed_run_does_not_create_assistant_message(
    api_client: APIClient,
    active_run: AgentRunRecord,
    session: AgentSession,
    domain_d_auth_header: dict[str, str],
) -> None:
    """FAILED callback records error details without creating assistant message."""
    payload = {
        "status": "failed",
        "error_code": "MODEL_PROVIDER_TIMEOUT",
        "error_message": "LLM provider timed out after 60s.",
        "step_count": 1,
        "prompt_tokens": 500,
        "completion_tokens": 0,
        "total_tokens": 500,
    }

    url = f"/api/v1/internal/runs/{active_run.id}/completion/"
    response = api_client.post(url, payload, format="json", **domain_d_auth_header)

    assert response.status_code == 200
    active_run.refresh_from_db()
    assert active_run.status == AgentRunStatus.FAILED
    assert active_run.error_code == "MODEL_PROVIDER_TIMEOUT"
    assert active_run.error_message == "LLM provider timed out after 60s."

    # Verify no assistant message was inserted
    assert (
        AgentSessionMessage.objects.filter(
            session=session, role=MessageRole.ASSISTANT
        ).count()
        == 0
    )


@pytest.mark.django_db
def test_idempotent_duplicate_completed_callback(
    api_client: APIClient,
    active_run: AgentRunRecord,
    session: AgentSession,
    domain_d_auth_header: dict[str, str],
) -> None:
    """Duplicate completion returns 200 idempotent=True, no mutation."""
    payload = {
        "status": "completed",
        "answer": "First execution answer.",
        "citations": [],
        "step_count": 2,
        "prompt_tokens": 800,
        "completion_tokens": 200,
        "total_tokens": 1000,
    }

    url = f"/api/v1/internal/runs/{active_run.id}/completion/"

    # First call -> 200 OK, idempotent=False
    resp1 = api_client.post(url, payload, format="json", **domain_d_auth_header)
    assert resp1.status_code == 200
    assert resp1.json()["idempotent"] is False

    active_run.refresh_from_db()
    original_finished_at = active_run.finished_at
    assert AgentSessionMessage.objects.filter(session=session).count() == 1

    # Second identical call -> 200 OK, idempotent=True
    resp2 = api_client.post(url, payload, format="json", **domain_d_auth_header)
    assert resp2.status_code == 200
    assert resp2.json()["idempotent"] is True

    # Ensure no duplicate message and no timestamp mutation
    active_run.refresh_from_db()
    assert active_run.finished_at == original_finished_at
    assert AgentSessionMessage.objects.filter(session=session).count() == 1


@pytest.mark.django_db
def test_conflicting_terminal_state_rejected_with_409(
    api_client: APIClient,
    active_run: AgentRunRecord,
    session: AgentSession,
    domain_d_auth_header: dict[str, str],
) -> None:
    """Conflicting COMPLETED callback on CANCELLED run returns 409."""
    # Set run to CANCELLED (e.g. cancelled by user)
    active_run.status = AgentRunStatus.CANCELLED
    active_run.error_code = "CANCELLED"
    active_run.error_message = "Cancelled by user."
    active_run.finished_at = timezone.now()
    active_run.save()

    # Agent Service asynchronously finishes later and attempts COMPLETED callback
    payload = {
        "status": "completed",
        "answer": "Late synthesized answer.",
        "citations": [],
        "step_count": 2,
    }

    url = f"/api/v1/internal/runs/{active_run.id}/completion/"
    response = api_client.post(url, payload, format="json", **domain_d_auth_header)

    assert response.status_code == 409
    data = response.json()
    assert data["error_code"] == "CONFLICTING_TERMINAL_STATE"
    assert data["status"] == "cancelled"

    # Confirm run remains CANCELLED in database and no assistant message is created
    active_run.refresh_from_db()
    assert active_run.status == AgentRunStatus.CANCELLED
    assert AgentSessionMessage.objects.filter(session=session).count() == 0


@pytest.mark.django_db
def test_completion_endpoint_requires_domain_d_auth(
    api_client: APIClient,
    active_run: AgentRunRecord,
) -> None:
    """Unauthenticated requests return 401 Unauthorized."""
    payload = {"status": "completed", "answer": "Answer"}
    url = f"/api/v1/internal/runs/{active_run.id}/completion/"

    response = api_client.post(url, payload, format="json")
    assert response.status_code == 401


@pytest.mark.django_db
def test_completion_endpoint_returns_404_for_nonexistent_run(
    api_client: APIClient,
    domain_d_auth_header: dict[str, str],
) -> None:
    """Non-existent run_id returns 404 Not Found."""
    payload = {"status": "completed", "answer": "Answer"}
    missing_id = uuid.uuid4()
    url = f"/api/v1/internal/runs/{missing_id}/completion/"

    response = api_client.post(url, payload, format="json", **domain_d_auth_header)
    assert response.status_code == 404
    assert response.json()["error_code"] == "RUN_NOT_FOUND"


@pytest.mark.django_db
def test_completion_endpoint_rejects_non_terminal_status(
    api_client: APIClient,
    active_run: AgentRunRecord,
    domain_d_auth_header: dict[str, str],
) -> None:
    """Non-terminal statuses are rejected with 400 Bad Request."""
    payload = {"status": "running"}
    url = f"/api/v1/internal/runs/{active_run.id}/completion/"

    response = api_client.post(url, payload, format="json", **domain_d_auth_header)
    assert response.status_code == 400
    assert "status" in response.json()
