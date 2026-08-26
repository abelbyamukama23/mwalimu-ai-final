"""Concurrency and race condition tests for run completion synchronization."""

from __future__ import annotations

import concurrent.futures
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
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

User = get_user_model()


@pytest.fixture
def institution(db: None) -> Institution:
    """Create a test institution."""
    return Institution.objects.create(
        name="Concurrency Test Institution",
        slug=f"concurrency-test-{uuid.uuid4().hex[:8]}",
    )


@pytest.fixture
def user(db: None, institution: Institution) -> User:
    """Create a test user."""
    return User.objects.create_user(
        email=f"concurrency_user_{uuid.uuid4().hex[:8]}@example.com",
        password="ValidPassword123!",
    )


@pytest.fixture
def session(db: None, user: User, institution: Institution) -> AgentSession:
    """Create a test agent session."""
    return AgentSession.objects.create(
        user=user,
        institution=institution,
        title="Concurrency Test Session",
        status=AgentSessionStatus.ACTIVE,
    )


@pytest.mark.django_db(transaction=True)
def test_concurrent_completions_on_distinct_runs_allocate_unique_sequences(
    session: AgentSession,
    user: User,
) -> None:
    """Two concurrent completions for different runs in the same session

    must allocate unique sequences without constraint violation.
    """
    run1 = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Prompt 1",
        status=AgentRunStatus.QUEUED,
    )
    run2 = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Prompt 2",
        status=AgentRunStatus.QUEUED,
    )

    token = mint_internal_service_jwt()

    def complete_run(run_id: uuid.UUID, answer: str) -> int:
        # Each thread gets its own DB connection
        connection.connect()
        client = APIClient()
        url = f"/api/v1/internal/runs/{run_id}/completion/"
        payload = {
            "status": "completed",
            "answer": answer,
            "citations": [],
            "step_count": 1,
        }
        res = client.post(
            url,
            payload,
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        return res.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future1 = executor.submit(complete_run, run1.id, "Answer for run 1")
        future2 = executor.submit(complete_run, run2.id, "Answer for run 2")
        status1 = future1.result(timeout=10)
        status2 = future2.result(timeout=10)

    assert status1 == 200
    assert status2 == 200

    # Verify both messages were created with distinct sequence numbers
    messages = list(
        AgentSessionMessage.objects.filter(
            session=session, role=MessageRole.ASSISTANT
        ).order_by("sequence")
    )
    assert len(messages) == 2
    sequences = [m.sequence for m in messages]
    assert len(set(sequences)) == 2  # No duplicate sequences
    assert set(sequences) == {0, 1}


@pytest.mark.django_db(transaction=True)
def test_concurrent_identical_completions_on_same_run_produces_single_message(
    session: AgentSession,
    user: User,
) -> None:
    """Two simultaneous completion requests for the exact same run

    must produce exactly one assistant message and succeed idempotently.
    """
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Prompt same run",
        status=AgentRunStatus.QUEUED,
    )

    token = mint_internal_service_jwt()

    def complete_same_run() -> int:
        connection.connect()
        client = APIClient()
        url = f"/api/v1/internal/runs/{run.id}/completion/"
        payload = {
            "status": "completed",
            "answer": "Identical answer",
            "citations": [],
            "step_count": 1,
        }
        res = client.post(
            url,
            payload,
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        return res.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future1 = executor.submit(complete_same_run)
        future2 = executor.submit(complete_same_run)
        status1 = future1.result(timeout=10)
        status2 = future2.result(timeout=10)

    assert status1 == 200
    assert status2 == 200

    # Exactly one assistant message should exist in the database
    messages = AgentSessionMessage.objects.filter(
        session=session, role=MessageRole.ASSISTANT
    )
    assert messages.count() == 1
    assert messages.first().run_id == run.id
