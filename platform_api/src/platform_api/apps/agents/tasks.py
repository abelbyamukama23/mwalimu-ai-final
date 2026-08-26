"""Celery tasks for Platform API watchdog reconciliation of orphaned agent runs."""

from __future__ import annotations

import datetime
import logging
from typing import Any

from celery import shared_task
from django.db import models, transaction
from django.utils import timezone

from .client import (
    AgentServiceClient,
    AgentServiceConnectionError,
    AgentServiceError,
    AgentServiceResponseError,
    AgentServiceTimeoutError,
    AgentServiceValidationError,
)
from .models import (
    TERMINAL_STATUSES,
    AgentRunRecord,
    AgentRunStatus,
    AgentSession,
    AgentSessionMessage,
    MessageRole,
)
from .views import _normalize_citations

logger = logging.getLogger(__name__)

QUEUED_TIMEOUT_SECONDS: float = 60.0
EXECUTION_GRACE_PERIOD_SECONDS: float = 30.0
DEFAULT_RECONCILIATION_BATCH_SIZE: int = 100


def _reconcile_single_run(
    run: AgentRunRecord,
    client: AgentServiceClient,
    now: datetime.datetime,
) -> str:
    """Probe and reconcile a single candidate orphaned agent run.

    Returns:
        Status string describing the outcome of reconciliation.
    """
    try:
        remote_resp = client.get_run_status(user_id=run.user_id, run_id=run.id)
        remote_status = remote_resp.status.lower()

        # If Agent Service reports the run is active, leave it active
        if remote_status not in TERMINAL_STATUSES:
            logger.info(
                "Watchdog probed run %s: still active on Agent Service (status=%s)",
                run.id,
                remote_status,
            )
            return f"active_{remote_status}"

        # If Agent Service reports a terminal status, reconcile into DB
        with transaction.atomic():
            locked_run = AgentRunRecord.objects.select_for_update().get(id=run.id)
            if locked_run.is_terminal:
                logger.info(
                    "Watchdog skipped run %s: already terminal (%s)",
                    locked_run.id,
                    locked_run.status,
                )
                return "already_terminal"

            locked_run.status = remote_status
            locked_run.answer = remote_resp.answer
            locked_run.citations = _normalize_citations(remote_resp.citations)
            locked_run.error_code = remote_resp.error_code
            locked_run.error_message = remote_resp.error_message
            locked_run.step_count = remote_resp.step_count
            locked_run.prompt_tokens = remote_resp.prompt_tokens
            locked_run.completion_tokens = remote_resp.completion_tokens
            locked_run.total_tokens = remote_resp.total_tokens
            if remote_resp.finished_at:
                try:
                    locked_run.finished_at = datetime.datetime.fromisoformat(
                        remote_resp.finished_at
                    )
                except Exception:
                    locked_run.finished_at = now
            else:
                locked_run.finished_at = now
            locked_run.save()

            if remote_status == AgentRunStatus.COMPLETED and locked_run.answer:
                session = AgentSession.objects.select_for_update().get(
                    id=locked_run.session_id
                )
                has_assistant = AgentSessionMessage.objects.filter(
                    session=session, run=locked_run, role=MessageRole.ASSISTANT
                ).exists()
                if not has_assistant:
                    max_seq = (
                        AgentSessionMessage.objects.filter(session=session)
                        .aggregate(models.Max("sequence"))
                        .get("sequence__max")
                    )
                    next_seq = 0 if max_seq is None else max_seq + 1
                    AgentSessionMessage.objects.create(
                        session=session,
                        run=locked_run,
                        role=MessageRole.ASSISTANT,
                        content=locked_run.answer,
                        citations=locked_run.citations,
                        sequence=next_seq,
                    )
                    logger.info(
                        "Watchdog created assistant message for run %s (seq=%d)",
                        locked_run.id,
                        next_seq,
                    )

            logger.info(
                "Watchdog successfully reconciled run %s to remote status %s",
                locked_run.id,
                remote_status,
            )
            return f"reconciled_{remote_status}"

    except AgentServiceResponseError as exc:
        if exc.status_code == 404:
            with transaction.atomic():
                locked_run = AgentRunRecord.objects.select_for_update().get(id=run.id)
                if locked_run.is_terminal:
                    return "already_terminal"

                if locked_run.status == AgentRunStatus.QUEUED:
                    locked_run.status = AgentRunStatus.FAILED
                    locked_run.error_code = "WORKER_UNAVAILABLE_OR_CRASHED"
                    locked_run.error_message = (
                        "Agent run expired in queue and was not found on worker."
                    )
                else:
                    locked_run.status = AgentRunStatus.TIMED_OUT
                    locked_run.error_code = "TIMEOUT"
                    locked_run.error_message = (
                        "Agent execution exceeded timeout and was not found on worker."
                    )
                locked_run.finished_at = now
                locked_run.save()

                logger.warning(
                    "Watchdog marked missing run %s as terminal (%s, error=%s)",
                    locked_run.id,
                    locked_run.status,
                    locked_run.error_code,
                )
                return f"reconciled_missing_{locked_run.status}"
        else:
            logger.error(
                "Watchdog probe for run %s returned unexpected HTTP %d: %s",
                run.id,
                exc.status_code,
                exc.detail,
            )
            return f"error_http_{exc.status_code}"

    except (AgentServiceConnectionError, AgentServiceTimeoutError) as exc:
        with transaction.atomic():
            locked_run = AgentRunRecord.objects.select_for_update().get(id=run.id)
            if locked_run.is_terminal:
                return "already_terminal"

            if locked_run.status == AgentRunStatus.QUEUED:
                locked_run.status = AgentRunStatus.FAILED
                locked_run.error_code = "WORKER_UNAVAILABLE_OR_CRASHED"
                locked_run.error_message = "Agent Service unreachable while run queued."
            else:
                locked_run.status = AgentRunStatus.TIMED_OUT
                locked_run.error_code = "TIMEOUT"
                locked_run.error_message = (
                    "Agent Service unreachable and execution exceeded timeout."
                )
            locked_run.finished_at = now
            locked_run.save()

            logger.warning(
                "Watchdog marked unreachable run %s as terminal (%s, error=%s): %s",
                locked_run.id,
                locked_run.status,
                locked_run.error_code,
                exc,
            )
            return f"reconciled_unreachable_{locked_run.status}"

    except (AgentServiceValidationError, AgentServiceError) as exc:
        logger.error(
            "Watchdog error probing run %s: %s",
            run.id,
            exc,
        )
        return "error_client"


@shared_task(  # type: ignore[untyped-decorator]
    name="platform_api.apps.agents.tasks.reconcile_orphaned_agent_runs",
    bind=True,
    max_retries=1,
)
def reconcile_orphaned_agent_runs(
    self: Any,
    batch_size: int = DEFAULT_RECONCILIATION_BATCH_SIZE,
    client: AgentServiceClient | None = None,
) -> dict[str, Any]:
    """Periodic Celery watchdog task for reconciling orphaned agent runs.

    Identifies and probes:
    1. QUEUED runs whose queued_at is older than 60 seconds.
    2. RUNNING runs whose started_at is older than timeout_seconds + 30s grace.

    Guarantees:
    - Bounded execution with batch limits.
    - Idempotent and concurrency-safe via select_for_update() row locking.
    - Preserves terminal runs without overwriting newer states.
    - Never logs secrets, credentials, or JWTs.
    """
    now = timezone.now()
    client_instance = client or AgentServiceClient()
    reconciliation_results: dict[str, int] = {}
    total_processed = 0

    # 1. Select candidate QUEUED runs beyond queue timeout threshold (60s)
    queued_cutoff = now - datetime.timedelta(seconds=QUEUED_TIMEOUT_SECONDS)
    queued_candidates = list(
        AgentRunRecord.objects.filter(
            status=AgentRunStatus.QUEUED,
            queued_at__lte=queued_cutoff,
        ).order_by("queued_at")[:batch_size]
    )

    for run in queued_candidates:
        result = _reconcile_single_run(run=run, client=client_instance, now=now)
        reconciliation_results[result] = reconciliation_results.get(result, 0) + 1
        total_processed += 1

    # 2. Select candidate RUNNING runs beyond started_at + timeout_seconds + 30s grace
    running_cutoff = now - datetime.timedelta(seconds=EXECUTION_GRACE_PERIOD_SECONDS)
    running_candidates = list(
        AgentRunRecord.objects.filter(
            status=AgentRunStatus.RUNNING,
            started_at__isnull=False,
            started_at__lte=running_cutoff,
        ).order_by("started_at")[:batch_size]
    )

    for run in running_candidates:
        if run.started_at is not None:
            deadline = run.started_at + datetime.timedelta(
                seconds=run.timeout_seconds + EXECUTION_GRACE_PERIOD_SECONDS
            )
            if now > deadline:
                result = _reconcile_single_run(run=run, client=client_instance, now=now)
                reconciliation_results[result] = (
                    reconciliation_results.get(result, 0) + 1
                )
                total_processed += 1

    logger.info(
        "Watchdog reconciliation cycle completed: %d runs processed, results=%s",
        total_processed,
        reconciliation_results,
    )
    return {
        "processed_count": total_processed,
        "results": reconciliation_results,
        "timestamp": now.isoformat(),
    }
