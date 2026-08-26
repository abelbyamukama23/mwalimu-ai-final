"""Tests for Celery watchdog crash recovery and run reconciliation."""

from __future__ import annotations

import datetime
import logging
import uuid
from unittest.mock import patch

import pytest
from django.utils import timezone

from platform_api.apps.agents.client import (
    AgentServiceClient,
    AgentServiceConnectionError,
    AgentServiceResponseError,
    AgentServiceRunResponse,
    AgentServiceTimeoutError,
)
from platform_api.apps.agents.models import (
    AgentRunRecord,
    AgentRunStatus,
    AgentSession,
    AgentSessionMessage,
    AgentSessionStatus,
    MessageRole,
)
from platform_api.apps.agents.tasks import (
    EXECUTION_GRACE_PERIOD_SECONDS,
    QUEUED_TIMEOUT_SECONDS,
    reconcile_orphaned_agent_runs,
)
from platform_api.apps.institutions.models import Institution
from platform_api.apps.libraries.models import Library
from platform_api.apps.users.models import User

# ---------------------------------------------------------------------------
# Fixtures & Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def institution(db: None) -> Institution:
    """Return a test institution."""
    return Institution.objects.create(
        name="Watchdog University",
        slug=f"watchdog-uni-{uuid.uuid4().hex[:6]}",
    )


@pytest.fixture
def user(db: None) -> User:
    """Return a test user."""
    return User.objects.create_user(
        email=f"watchdog_{uuid.uuid4().hex[:6]}@example.com",
        password="TestPassword123!",
    )


@pytest.fixture
def library(db: None, institution: Institution) -> Library:
    """Return a test library."""
    return Library.objects.create(
        institution=institution,
        name="Watchdog Library",
        slug=f"watchdog-lib-{uuid.uuid4().hex[:6]}",
    )


@pytest.fixture
def session(
    db: None, user: User, institution: Institution, library: Library
) -> AgentSession:
    """Return a test agent session."""
    return AgentSession.objects.create(
        user=user,
        institution=institution,
        primary_library=library,
        title="Watchdog Session",
        status=AgentSessionStatus.ACTIVE,
    )


# ---------------------------------------------------------------------------
# Timeout Semantics Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_queued_run_below_60s_untouched(session: AgentSession, user: User) -> None:
    """A QUEUED run below 60 seconds is untouched and not probed."""
    now = timezone.now()
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Recent queued run",
        status=AgentRunStatus.QUEUED,
        queued_at=now - datetime.timedelta(seconds=30),
    )

    with patch.object(AgentServiceClient, "get_run_status") as mock_probe:
        result = reconcile_orphaned_agent_runs()
        mock_probe.assert_not_called()

    run.refresh_from_db()
    assert run.status == AgentRunStatus.QUEUED
    assert result["processed_count"] == 0


@pytest.mark.django_db
def test_queued_run_beyond_60s_probed(session: AgentSession, user: User) -> None:
    """A QUEUED run older than 60 seconds is probed by the watchdog."""
    now = timezone.now()
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Old queued run",
        status=AgentRunStatus.QUEUED,
        queued_at=now - datetime.timedelta(seconds=QUEUED_TIMEOUT_SECONDS + 10),
    )

    mock_resp = AgentServiceRunResponse(
        id=run.id,
        session_id=session.id,
        status="queued",
        prompt=run.prompt,
        created_at=now.isoformat(),
    )

    with patch.object(
        AgentServiceClient, "get_run_status", return_value=mock_resp
    ) as mock_probe:
        result = reconcile_orphaned_agent_runs()
        mock_probe.assert_called_once_with(user_id=user.pk, run_id=run.id)

    run.refresh_from_db()
    assert run.status == AgentRunStatus.QUEUED
    assert result["processed_count"] == 1


@pytest.mark.django_db
def test_running_run_below_execution_timeout_untouched(
    session: AgentSession, user: User
) -> None:
    """A RUNNING run below its execution timeout is untouched."""
    now = timezone.now()
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Active running run",
        status=AgentRunStatus.RUNNING,
        timeout_seconds=60.0,
        started_at=now - datetime.timedelta(seconds=30),
    )

    with patch.object(AgentServiceClient, "get_run_status") as mock_probe:
        result = reconcile_orphaned_agent_runs()
        mock_probe.assert_not_called()

    run.refresh_from_db()
    assert run.status == AgentRunStatus.RUNNING
    assert result["processed_count"] == 0


@pytest.mark.django_db
def test_running_run_beyond_timeout_plus_30s_grace_probed(
    session: AgentSession, user: User
) -> None:
    """A RUNNING run beyond timeout + 30s grace period is probed."""
    now = timezone.now()
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Expired running run",
        status=AgentRunStatus.RUNNING,
        timeout_seconds=60.0,
        started_at=now
        - datetime.timedelta(seconds=60.0 + EXECUTION_GRACE_PERIOD_SECONDS + 10),
    )

    mock_resp = AgentServiceRunResponse(
        id=run.id,
        session_id=session.id,
        status="running",
        prompt=run.prompt,
        created_at=now.isoformat(),
    )

    with patch.object(
        AgentServiceClient, "get_run_status", return_value=mock_resp
    ) as mock_probe:
        result = reconcile_orphaned_agent_runs()
        mock_probe.assert_called_once_with(user_id=user.pk, run_id=run.id)

    run.refresh_from_db()
    assert run.status == AgentRunStatus.RUNNING
    assert result["processed_count"] == 1


@pytest.mark.django_db
def test_created_at_not_incorrectly_used_for_execution_timeout(
    session: AgentSession, user: User
) -> None:
    """Old created_at with recent started_at must not be treated as expired."""
    now = timezone.now()
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Run with long queue wait",
        status=AgentRunStatus.RUNNING,
        timeout_seconds=60.0,
        created_at=now - datetime.timedelta(seconds=200),
        queued_at=now - datetime.timedelta(seconds=150),
        started_at=now - datetime.timedelta(seconds=10),  # Only 10s running!
    )

    with patch.object(AgentServiceClient, "get_run_status") as mock_probe:
        result = reconcile_orphaned_agent_runs()
        mock_probe.assert_not_called()

    run.refresh_from_db()
    assert run.status == AgentRunStatus.RUNNING
    assert result["processed_count"] == 0


# ---------------------------------------------------------------------------
# Probe Interpretation Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_agent_service_reports_active_run_durable_state_unchanged(
    session: AgentSession, user: User
) -> None:
    """If Agent Service responds that run is still actively running, leave active."""
    now = timezone.now()
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Run still in flight",
        status=AgentRunStatus.RUNNING,
        timeout_seconds=60.0,
        started_at=now - datetime.timedelta(seconds=100),
    )

    mock_resp = AgentServiceRunResponse(
        id=run.id,
        session_id=session.id,
        status="running",
        prompt=run.prompt,
        created_at=now.isoformat(),
    )

    with patch.object(AgentServiceClient, "get_run_status", return_value=mock_resp):
        reconcile_orphaned_agent_runs()

    run.refresh_from_db()
    assert run.status == AgentRunStatus.RUNNING


@pytest.mark.django_db
def test_agent_service_reports_terminal_completion_safely_reconciled(
    session: AgentSession, user: User, library: Library
) -> None:
    """If Agent Service reports COMPLETED, sync answer, metrics, and transcript."""
    now = timezone.now()
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Explain glycolysis.",
        status=AgentRunStatus.RUNNING,
        timeout_seconds=60.0,
        started_at=now - datetime.timedelta(seconds=100),
    )

    citation_dict = {
        "resource_id": str(uuid.uuid4()),
        "resource_name": "Biochemistry",
        "library_id": str(library.id),
        "library_name": library.name,
        "sequence": 1,
    }

    mock_resp = AgentServiceRunResponse(
        id=run.id,
        session_id=session.id,
        status="completed",
        prompt=run.prompt,
        answer="Glycolysis breaks down glucose into pyruvate.",
        citations=[citation_dict],
        step_count=2,
        prompt_tokens=400,
        completion_tokens=100,
        total_tokens=500,
        created_at=now.isoformat(),
        finished_at=now.isoformat(),
    )

    with patch.object(AgentServiceClient, "get_run_status", return_value=mock_resp):
        result = reconcile_orphaned_agent_runs()

    assert result["results"]["reconciled_completed"] == 1

    run.refresh_from_db()
    assert run.status == AgentRunStatus.COMPLETED
    assert run.answer == "Glycolysis breaks down glucose into pyruvate."
    assert run.step_count == 2
    assert run.total_tokens == 500
    assert len(run.citations) == 1

    # Verify canonical assistant message was inserted
    messages = AgentSessionMessage.objects.filter(
        session=session, role=MessageRole.ASSISTANT
    )
    assert messages.count() == 1
    assert messages.first().content == run.answer


@pytest.mark.django_db
def test_agent_service_returns_404_queued_run_marked_failed(
    session: AgentSession, user: User
) -> None:
    """A QUEUED run returning 404 from Agent Service transitions to FAILED."""
    now = timezone.now()
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Missing queued run",
        status=AgentRunStatus.QUEUED,
        queued_at=now - datetime.timedelta(seconds=70),
    )

    with patch.object(
        AgentServiceClient,
        "get_run_status",
        side_effect=AgentServiceResponseError(status_code=404, detail="Run not found"),
    ):
        reconcile_orphaned_agent_runs()

    run.refresh_from_db()
    assert run.status == AgentRunStatus.FAILED
    assert run.error_code == "WORKER_UNAVAILABLE_OR_CRASHED"
    assert run.finished_at is not None


@pytest.mark.django_db
def test_agent_service_returns_404_running_run_marked_timed_out(
    session: AgentSession, user: User
) -> None:
    """A RUNNING run returning 404 from Agent Service transitions to TIMED_OUT."""
    now = timezone.now()
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Missing running run",
        status=AgentRunStatus.RUNNING,
        timeout_seconds=60.0,
        started_at=now - datetime.timedelta(seconds=100),
    )

    with patch.object(
        AgentServiceClient,
        "get_run_status",
        side_effect=AgentServiceResponseError(status_code=404, detail="Run not found"),
    ):
        reconcile_orphaned_agent_runs()

    run.refresh_from_db()
    assert run.status == AgentRunStatus.TIMED_OUT
    assert run.error_code == "TIMEOUT"
    assert run.finished_at is not None


@pytest.mark.django_db
def test_agent_service_connection_failure_handled_safely(
    session: AgentSession, user: User
) -> None:
    """Connection failure during watchdog probe transitions expired run to terminal."""
    now = timezone.now()
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Unreachable run",
        status=AgentRunStatus.RUNNING,
        timeout_seconds=60.0,
        started_at=now - datetime.timedelta(seconds=100),
    )

    with patch.object(
        AgentServiceClient,
        "get_run_status",
        side_effect=AgentServiceConnectionError("Connection refused"),
    ):
        reconcile_orphaned_agent_runs()

    run.refresh_from_db()
    assert run.status == AgentRunStatus.TIMED_OUT
    assert run.error_code == "TIMEOUT"


@pytest.mark.django_db
def test_agent_service_timeout_handled_safely(
    session: AgentSession, user: User
) -> None:
    """Timeout during watchdog probe transitions expired run to terminal."""
    now = timezone.now()
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Probe timeout run",
        status=AgentRunStatus.QUEUED,
        queued_at=now - datetime.timedelta(seconds=80),
    )

    with patch.object(
        AgentServiceClient,
        "get_run_status",
        side_effect=AgentServiceTimeoutError("Probe timed out"),
    ):
        reconcile_orphaned_agent_runs()

    run.refresh_from_db()
    assert run.status == AgentRunStatus.FAILED
    assert run.error_code == "WORKER_UNAVAILABLE_OR_CRASHED"


# ---------------------------------------------------------------------------
# Terminal State Invariance & Concurrency Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_already_completed_run_remains_completed(
    session: AgentSession, user: User
) -> None:
    """Completed run is untouched even if queried by watchdog."""
    now = timezone.now()
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Completed run",
        status=AgentRunStatus.COMPLETED,
        answer="Existing answer",
        queued_at=now - datetime.timedelta(seconds=100),
    )

    reconcile_orphaned_agent_runs()

    run.refresh_from_db()
    assert run.status == AgentRunStatus.COMPLETED
    assert run.answer == "Existing answer"


@pytest.mark.django_db
def test_already_cancelled_run_remains_cancelled(
    session: AgentSession, user: User
) -> None:
    """Cancelled run is untouched and cannot be modified by watchdog."""
    now = timezone.now()
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Cancelled run",
        status=AgentRunStatus.CANCELLED,
        error_code="CANCELLED",
        queued_at=now - datetime.timedelta(seconds=100),
    )

    reconcile_orphaned_agent_runs()

    run.refresh_from_db()
    assert run.status == AgentRunStatus.CANCELLED


@pytest.mark.django_db
def test_cancellation_watchdog_race_is_safe(session: AgentSession, user: User) -> None:
    """If run is cancelled concurrently while watchdog probes, CANCELLED wins."""
    now = timezone.now()
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Race run",
        status=AgentRunStatus.RUNNING,
        timeout_seconds=60.0,
        started_at=now - datetime.timedelta(seconds=100),
    )

    def probe_with_concurrent_cancel(
        user_id: uuid.UUID | str, run_id: uuid.UUID | str
    ) -> AgentServiceRunResponse:
        # Simulate user cancelling during probe execution
        AgentRunRecord.objects.filter(id=run.id).update(
            status=AgentRunStatus.CANCELLED,
            error_code="CANCELLED",
            finished_at=timezone.now(),
        )
        return AgentServiceRunResponse(
            id=run.id,
            session_id=session.id,
            status="completed",
            prompt=run.prompt,
            answer="Late answer",
            created_at=now.isoformat(),
        )

    with patch.object(
        AgentServiceClient, "get_run_status", side_effect=probe_with_concurrent_cancel
    ):
        reconcile_orphaned_agent_runs()

    run.refresh_from_db()
    # CANCELLED must be preserved!
    assert run.status == AgentRunStatus.CANCELLED
    assert (
        AgentSessionMessage.objects.filter(
            session=session, role=MessageRole.ASSISTANT
        ).count()
        == 0
    )


@pytest.mark.django_db
def test_duplicate_watchdog_execution_is_idempotent(
    session: AgentSession, user: User
) -> None:
    """Multiple sequential runs of the watchdog produce idempotent results."""
    now = timezone.now()
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Idempotent run",
        status=AgentRunStatus.QUEUED,
        queued_at=now - datetime.timedelta(seconds=70),
    )

    with patch.object(
        AgentServiceClient,
        "get_run_status",
        side_effect=AgentServiceResponseError(status_code=404, detail="Not found"),
    ):
        # Run 1
        res1 = reconcile_orphaned_agent_runs()
        assert res1["processed_count"] == 1

        # Run 2 -> candidate is already terminal (FAILED), so processed_count is 0
        res2 = reconcile_orphaned_agent_runs()
        assert res2["processed_count"] == 0

    run.refresh_from_db()
    assert run.status == AgentRunStatus.FAILED


@pytest.mark.django_db
def test_no_duplicate_assistant_transcript_message_created(
    session: AgentSession, user: User
) -> None:
    """Watchdog reconciliation of completed run never duplicates assistant msg."""
    now = timezone.now()
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="No duplicate transcript",
        status=AgentRunStatus.RUNNING,
        timeout_seconds=60.0,
        started_at=now - datetime.timedelta(seconds=100),
    )

    mock_resp = AgentServiceRunResponse(
        id=run.id,
        session_id=session.id,
        status="completed",
        prompt=run.prompt,
        answer="Definitive answer",
        created_at=now.isoformat(),
    )

    with patch.object(AgentServiceClient, "get_run_status", return_value=mock_resp):
        reconcile_orphaned_agent_runs()
        reconcile_orphaned_agent_runs()

    messages = AgentSessionMessage.objects.filter(
        session=session, role=MessageRole.ASSISTANT
    )
    assert messages.count() == 1
    assert messages.first().content == "Definitive answer"


# ---------------------------------------------------------------------------
# Security & Observability Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_watchdog_does_not_expose_credentials_in_logs(
    session: AgentSession,
    user: User,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Watchdog logs contain no JWTs, API keys, or tokens."""
    now = timezone.now()
    AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Log safety run",
        status=AgentRunStatus.QUEUED,
        queued_at=now - datetime.timedelta(seconds=70),
    )

    mock_resp = AgentServiceRunResponse(
        id=uuid.uuid4(),
        session_id=session.id,
        status="queued",
        prompt="Log safety run",
        created_at=now.isoformat(),
    )

    with (
        caplog.at_level(logging.DEBUG),
        patch.object(AgentServiceClient, "get_run_status", return_value=mock_resp),
    ):
        reconcile_orphaned_agent_runs()

    log_text = caplog.text.lower()
    assert (
        "jwt" not in log_text or "agent_service_jwt" in log_text
    )  # settings names only
    assert "bearer " not in log_text
    assert "secret" not in log_text
    assert "deepseek" not in log_text
    assert "delegated" not in log_text or "delegated_token" not in log_text


@pytest.mark.django_db
def test_already_failed_run_remains_failed(session: AgentSession, user: User) -> None:
    """Already FAILED run is untouched and cannot be modified by watchdog."""
    now = timezone.now()
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Failed run",
        status=AgentRunStatus.FAILED,
        error_code="EXISTING_FAILURE",
        queued_at=now - datetime.timedelta(seconds=100),
    )

    reconcile_orphaned_agent_runs()

    run.refresh_from_db()
    assert run.status == AgentRunStatus.FAILED
    assert run.error_code == "EXISTING_FAILURE"


@pytest.mark.django_db
def test_already_timed_out_run_remains_timed_out(
    session: AgentSession, user: User
) -> None:
    """Already TIMED_OUT run is untouched and cannot be modified by watchdog."""
    now = timezone.now()
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Timed out run",
        status=AgentRunStatus.TIMED_OUT,
        error_code="TIMEOUT",
        queued_at=now - datetime.timedelta(seconds=100),
    )

    reconcile_orphaned_agent_runs()

    run.refresh_from_db()
    assert run.status == AgentRunStatus.TIMED_OUT
    assert run.error_code == "TIMEOUT"


@pytest.mark.django_db
def test_completion_watchdog_race_is_safe(session: AgentSession, user: User) -> None:
    """If run completes concurrently while watchdog probes, completion wins."""
    now = timezone.now()
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Completion race run",
        status=AgentRunStatus.RUNNING,
        timeout_seconds=60.0,
        started_at=now - datetime.timedelta(seconds=100),
    )

    def probe_with_concurrent_completion(
        user_id: uuid.UUID | str, run_id: uuid.UUID | str
    ) -> AgentServiceRunResponse:
        # Simulate completion callback arriving during probe
        AgentRunRecord.objects.filter(id=run.id).update(
            status=AgentRunStatus.COMPLETED,
            answer="Answer arrived first",
            finished_at=timezone.now(),
        )
        return AgentServiceRunResponse(
            id=run.id,
            session_id=session.id,
            status="completed",
            prompt=run.prompt,
            answer="Late answer",
            created_at=now.isoformat(),
        )

    with patch.object(
        AgentServiceClient,
        "get_run_status",
        side_effect=probe_with_concurrent_completion,
    ):
        reconcile_orphaned_agent_runs()

    run.refresh_from_db()
    assert run.status == AgentRunStatus.COMPLETED
    assert run.answer == "Answer arrived first"


@pytest.mark.django_db
def test_queued_at_used_for_queue_timeout(session: AgentSession, user: User) -> None:
    """Queue timeout depends strictly on queued_at, not created_at."""
    now = timezone.now()
    # created_at is 100s ago, but queued_at is 10s ago
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Recent queue run",
        status=AgentRunStatus.QUEUED,
        created_at=now - datetime.timedelta(seconds=100),
        queued_at=now - datetime.timedelta(seconds=10),
    )

    with patch.object(AgentServiceClient, "get_run_status") as mock_probe:
        result = reconcile_orphaned_agent_runs()
        mock_probe.assert_not_called()

    run.refresh_from_db()
    assert run.status == AgentRunStatus.QUEUED
    assert result["processed_count"] == 0


@pytest.mark.django_db
def test_started_at_used_for_execution_timeout(
    session: AgentSession, user: User
) -> None:
    """Execution timeout depends strictly on started_at, not queued_at."""
    now = timezone.now()
    # queued_at is 200s ago, but started_at is only 15s ago
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Recent start run",
        status=AgentRunStatus.RUNNING,
        timeout_seconds=60.0,
        queued_at=now - datetime.timedelta(seconds=200),
        started_at=now - datetime.timedelta(seconds=15),
    )

    with patch.object(AgentServiceClient, "get_run_status") as mock_probe:
        result = reconcile_orphaned_agent_runs()
        mock_probe.assert_not_called()

    run.refresh_from_db()
    assert run.status == AgentRunStatus.RUNNING
    assert result["processed_count"] == 0
