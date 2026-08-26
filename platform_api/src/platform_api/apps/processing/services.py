"""Processing service for document parsing and reprocessing workflows."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.db import transaction

from platform_api.apps.resources.models import Resource

from .indexing import activate_run
from .models import ProcessingRun, ProcessingStatus
from .tasks import _get_extractor_version, process_resource_run

logger = logging.getLogger(__name__)


def enqueue_processing(
    resource: Resource,
    pipeline_version: str | None = None,
    extractor_version: str | None = None,
    chunker_version: str | None = None,
    embedding_model: str | None = None,
    embedding_version: str | None = None,
    embedding_dimensions: int | None = None,
) -> ProcessingRun:
    """Idempotently enqueue a document processing run for a resource.

    If a READY processing run with the identical identity already exists:
    - If inactive, it is activated.
    - It is returned immediately without re-processing.

    If a run with the identical identity is currently QUEUED or PROCESSING:
    - It is returned immediately to prevent duplicate task execution.

    Otherwise, a new ProcessingRun is created and dispatched to Celery.

    Args:
        resource: Target Resource model instance.
        pipeline_version: Optional override for pipeline version.
        extractor_version: Optional override for extractor version.
        chunker_version: Optional override for chunker version.
        embedding_model: Optional override for embedding model.
        embedding_version: Optional override for embedding version.
        embedding_dimensions: Optional override for vector dimensions.

    Returns:
        The existing or newly created ProcessingRun.
    """
    source_checksum = resource.checksum
    p_version = pipeline_version or str(getattr(settings, "PIPELINE_VERSION", "1"))
    e_version = extractor_version or _get_extractor_version(resource.resource_type)
    c_version = chunker_version or str(getattr(settings, "CHUNKER_VERSION", "1"))
    emb_model = embedding_model or str(
        getattr(settings, "EMBEDDING_MODEL", "text-embedding-3-small")
    )
    emb_version = embedding_version or str(getattr(settings, "EMBEDDING_VERSION", "1"))
    emb_dims = (
        embedding_dimensions
        if embedding_dimensions is not None
        else int(getattr(settings, "EMBEDDING_DIMENSIONS", 1536))
    )

    identity_kwargs: dict[str, Any] = {
        "resource": resource,
        "source_checksum": source_checksum,
        "pipeline_version": p_version,
        "extractor_version": e_version,
        "chunker_version": c_version,
        "embedding_model": emb_model,
        "embedding_version": emb_version,
    }

    # Check for existing READY run with identical identity
    existing_ready = ProcessingRun.objects.filter(
        status=ProcessingStatus.READY,
        **identity_kwargs,
    ).first()

    if existing_ready:
        if not existing_ready.is_active:
            activate_run(existing_ready)
        logger.info(
            "Reusing existing READY ProcessingRun %s for resource %s",
            existing_ready.id,
            resource.id,
        )
        return existing_ready

    # Check for existing in-flight run with identical identity
    in_flight = ProcessingRun.objects.filter(
        status__in=[ProcessingStatus.QUEUED, ProcessingStatus.PROCESSING],
        **identity_kwargs,
    ).first()

    if in_flight:
        logger.info(
            "ProcessingRun %s is already in-flight for resource %s",
            in_flight.id,
            resource.id,
        )
        return in_flight

    with transaction.atomic():
        run = ProcessingRun.objects.create(
            resource=resource,
            library=resource.library,
            status=ProcessingStatus.QUEUED,
            source_checksum=source_checksum,
            pipeline_version=p_version,
            extractor_version=e_version,
            chunker_version=c_version,
            embedding_model=emb_model,
            embedding_version=emb_version,
            embedding_dimensions=emb_dims,
            is_active=False,
        )

    # Dispatch Celery task
    try:
        task_res = process_resource_run.delay(str(run.id))
        run.celery_task_id = task_res.id
        run.save(update_fields=["celery_task_id", "updated_at"])
    except Exception as exc:
        logger.warning(
            "Could not dispatch Celery task asynchronously for run %s: %s",
            run.id,
            exc,
        )

    return run
