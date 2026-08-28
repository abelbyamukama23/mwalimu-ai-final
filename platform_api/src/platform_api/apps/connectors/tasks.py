"""Celery tasks for connector synchronization."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from celery import shared_task
from django.utils import timezone

from .adapters import UnsupportedConnectorError, get_connector_adapter
from .models import (
    Connection,
    ConnectionStatus,
    ConnectionSyncJob,
    SyncJobStatus,
    SyncStatus,
)

logger = logging.getLogger(__name__)


@shared_task(  # type: ignore[untyped-decorator]
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=3,
    soft_time_limit=600,
    time_limit=900,
    queue="ingestion",
)
def sync_connection_task(self: Any, connection_id: str, sync_job_id: str) -> None:
    """Execute asynchronous synchronization for a library connection."""
    try:
        conn_uuid = uuid.UUID(str(connection_id))
        job_uuid = uuid.UUID(str(sync_job_id))
    except (ValueError, TypeError):
        logger.error(
            "Invalid UUID parameters: connection_id=%s, sync_job_id=%s",
            connection_id,
            sync_job_id,
        )
        return

    try:
        connection = Connection.objects.select_related("connector", "library").get(
            id=conn_uuid
        )
    except Connection.DoesNotExist:
        logger.error("Connection %s not found.", connection_id)
        return

    try:
        sync_job = ConnectionSyncJob.objects.get(id=job_uuid)
    except ConnectionSyncJob.DoesNotExist:
        logger.error("ConnectionSyncJob %s not found.", sync_job_id)
        return

    # Update job to RUNNING
    sync_job.status = SyncJobStatus.RUNNING
    sync_job.celery_task_id = self.request.id
    sync_job.started_at = timezone.now()
    sync_job.save(
        update_fields=["status", "celery_task_id", "started_at", "updated_at"]
    )

    connection.status = ConnectionStatus.SYNCING
    connection.save(update_fields=["status", "updated_at"])

    try:
        adapter = get_connector_adapter(connection.connector.connector_type)
        result = adapter.sync(connection, sync_job)

        # Update sync job counters and completion
        sync_job.resources_discovered = result.resources_discovered
        sync_job.resources_created = result.resources_created
        sync_job.resources_updated = result.resources_updated
        sync_job.resources_deleted = result.resources_deleted
        sync_job.finished_at = timezone.now()

        if result.is_success:
            sync_job.status = SyncJobStatus.COMPLETED
            sync_job.error_code = None
            sync_job.error_message = ""
            connection.status = ConnectionStatus.ACTIVE
            connection.last_sync_status = SyncStatus.SUCCESS
            connection.last_sync_error = ""
        else:
            sync_job.status = SyncJobStatus.FAILED
            sync_job.error_code = result.error_code
            sync_job.error_message = result.error_message
            connection.status = ConnectionStatus.ERROR
            connection.last_sync_status = SyncStatus.FAILED
            connection.last_sync_error = result.error_message

        sync_job.save()

        connection.last_synced_at = timezone.now()
        connection.save(
            update_fields=[
                "status",
                "last_synced_at",
                "last_sync_status",
                "last_sync_error",
                "updated_at",
            ]
        )

        logger.info(
            "Completed sync task for connection %s: discovered=%d, created=%d, updated=%d",
            connection.id,
            result.resources_discovered,
            result.resources_created,
            result.resources_updated,
        )

    except UnsupportedConnectorError as exc:
        logger.error("Unsupported connector type for connection %s: %s", connection.id, exc)
        _record_failure(connection, sync_job, "UNSUPPORTED_CONNECTOR", str(exc))
    except Exception as exc:
        logger.exception("Unexpected error in sync task for connection %s: %s", connection.id, exc)
        _record_failure(connection, sync_job, "UNKNOWN_ERROR", str(exc))


def _record_failure(
    connection: Connection,
    sync_job: ConnectionSyncJob,
    error_code: str,
    error_message: str,
) -> None:
    """Record terminal failure status on both sync job and connection."""
    now = timezone.now()
    sync_job.status = SyncJobStatus.FAILED
    sync_job.error_code = error_code
    sync_job.error_message = error_message
    sync_job.finished_at = now
    sync_job.save(
        update_fields=[
            "status",
            "error_code",
            "error_message",
            "finished_at",
            "updated_at",
        ]
    )

    connection.status = ConnectionStatus.ERROR
    connection.last_synced_at = now
    connection.last_sync_status = SyncStatus.FAILED
    connection.last_sync_error = error_message
    connection.save(
        update_fields=[
            "status",
            "last_synced_at",
            "last_sync_status",
            "last_sync_error",
            "updated_at",
        ]
    )
