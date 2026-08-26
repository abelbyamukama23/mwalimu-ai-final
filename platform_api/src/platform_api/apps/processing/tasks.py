"""Celery tasks for document processing and knowledge indexing."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import redis
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from platform_api.apps.resources.object_key import validate_object_key
from platform_api.apps.resources.storage import get_object_storage

from .chunker import chunk
from .embedding import get_embedding_provider
from .extractors import ExtractionError, extract
from .extractors.docx import EXTRACTOR_VERSION_DOCX
from .extractors.pdf import EXTRACTOR_VERSION_PDF
from .extractors.txt import EXTRACTOR_VERSION_TXT
from .indexing import activate_run, write_chunks_and_embeddings
from .models import DocumentChunk, ProcessingRun, ProcessingStage, ProcessingStatus
from .normalizer import normalize

logger = logging.getLogger(__name__)


def _get_extractor_version(resource_type: str) -> str:
    """Return the version string for the specific resource type extractor."""
    versions = {
        "pdf": EXTRACTOR_VERSION_PDF,
        "docx": EXTRACTOR_VERSION_DOCX,
        "txt": EXTRACTOR_VERSION_TXT,
    }
    return versions.get(resource_type, "unknown-1")


def _acquire_redis_lock(
    redis_client: Any | None, lock_key: str, timeout: int = 900
) -> bool:
    """Acquire an opportunistic Redis lock for concurrency control."""
    if redis_client is None:
        return True
    try:
        acquired = redis_client.set(lock_key, "1", nx=True, ex=timeout)
        return bool(acquired)
    except Exception as exc:
        logger.warning("Redis lock error (proceeding due to DB constraints): %s", exc)
        return True


def _release_redis_lock(redis_client: Any | None, lock_key: str) -> None:
    """Release an opportunistic Redis lock."""
    if redis_client is None:
        return
    try:
        redis_client.delete(lock_key)
    except Exception as exc:
        logger.warning("Redis release lock error: %s", exc)


@shared_task(  # type: ignore[untyped-decorator]
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=5,
    soft_time_limit=600,
    time_limit=900,
    queue="ingestion",
)
def process_resource_run(self: Any, run_id: str) -> None:
    """Orchestrate end-to-end document processing for a ProcessingRun.

    Stages:
    1. Integrity check: verify resource, library relationship, object key
    2. Extraction: parse original binary into structured pages
    3. Normalization: clean text while retaining provenance
    4. Chunking: split into deterministic chunks
    5. Embedding: batch generate dense vector embeddings
    6. Indexing & Activation: transactionally persist and activate run
    """
    try:
        run_uuid = uuid.UUID(str(run_id))
    except (ValueError, TypeError):
        logger.error("Invalid run_id: %s", run_id)
        return

    try:
        run = ProcessingRun.objects.select_related("resource", "library").get(
            pk=run_uuid
        )
    except ProcessingRun.DoesNotExist:
        logger.error("ProcessingRun %s not found.", run_id)
        return

    # Check if run is already ready
    if run.status == ProcessingStatus.READY and run.is_active:
        logger.info("ProcessingRun %s is already READY and active. Skipping.", run_id)
        return

    # Update task correlation
    run.celery_task_id = self.request.id
    run.attempt_count += 1
    run.started_at = timezone.now()
    run.status = ProcessingStatus.PROCESSING
    run.save(
        update_fields=[
            "celery_task_id",
            "attempt_count",
            "started_at",
            "status",
            "updated_at",
        ]
    )

    redis_client = None
    lock_key = f"lock:resource:{run.resource_id}:process"
    try:
        broker_url = getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0")
        if broker_url.startswith("redis"):
            redis_client = redis.from_url(broker_url)  # type: ignore[no-untyped-call]
    except Exception as exc:
        logger.warning("Could not initialize Redis client for lock: %s", exc)

    _acquire_redis_lock(redis_client, lock_key, timeout=900)

    try:
        # --- Stage 1: Integrity Verification ---
        resource = run.resource
        if resource.library_id != run.library_id:
            raise ValueError(
                f"Integrity violation: resource library {resource.library_id} "
                f"!= run library {run.library_id}"
            )

        validate_object_key(resource.object_key, resource.library_id)

        # --- Stage 2: Extraction ---
        run.current_stage = ProcessingStage.EXTRACT
        run.save(update_fields=["current_stage", "updated_at"])

        storage = get_object_storage()
        try:
            stream = storage.download(resource.object_key)
            raw_bytes = stream.read()
        except Exception as exc:
            raise ExtractionError(
                f"Failed to read resource binary from storage: {exc}"
            ) from exc

        extracted_doc = extract(raw_bytes, resource.resource_type)
        if extracted_doc.is_empty:
            raise ExtractionError("EMPTY_EXTRACTION")

        # --- Stage 3: Normalization ---
        run.current_stage = ProcessingStage.NORMALIZE
        run.save(update_fields=["current_stage", "updated_at"])

        normalized_doc = normalize(extracted_doc)
        if normalized_doc.is_empty:
            raise ExtractionError("EMPTY_EXTRACTION")

        # --- Stage 4: Chunking ---
        run.current_stage = ProcessingStage.CHUNK
        run.save(update_fields=["current_stage", "updated_at"])

        chunks = chunk(normalized_doc)
        if not chunks:
            raise ExtractionError("EMPTY_EXTRACTION")

        # --- Stage 5: Embedding ---
        run.current_stage = ProcessingStage.EMBED
        run.save(update_fields=["current_stage", "updated_at"])

        provider = get_embedding_provider()
        chunk_texts = [c.text for c in chunks]
        vectors = provider.embed_texts(chunk_texts)

        # --- Stage 6: Index & Activate ---
        run.current_stage = ProcessingStage.INDEX
        run.save(update_fields=["current_stage", "updated_at"])

        with transaction.atomic():
            write_chunks_and_embeddings(run, chunks, vectors)
            activate_run(run)

        run.current_stage = ProcessingStage.FINALIZE
        run.save(update_fields=["current_stage", "updated_at"])
        logger.info("Successfully processed and activated ProcessingRun %s", run_id)

    except ExtractionError as exc:
        is_empty = str(exc) == "EMPTY_EXTRACTION"
        error_code = "EMPTY_EXTRACTION" if is_empty else "EXTRACTION_FAILED"
        error_msg = (
            "Document produced no usable extracted text." if is_empty else str(exc)
        )
        _handle_permanent_failure(run, error_code=error_code, error_message=error_msg)
    except SoftTimeLimitExceeded:
        _handle_permanent_failure(
            run,
            error_code="TIMEOUT",
            error_message="Processing exceeded time limit.",
        )
    except Exception as exc:
        logger.exception(
            "Unexpected error in processing task for run %s: %s", run_id, exc
        )
        # Determine if transient and retry
        if self.request.retries < self.max_retries:
            countdown = int((2**self.request.retries) * 5)
            raise self.retry(exc=exc, countdown=countdown) from exc
        else:
            _handle_permanent_failure(
                run,
                error_code="UNKNOWN",
                error_message=f"Processing failed after max retries: {exc}",
            )
    finally:
        _release_redis_lock(redis_client, lock_key)


def _handle_permanent_failure(
    run: ProcessingRun, error_code: str, error_message: str
) -> None:
    """Mark a ProcessingRun as failed, record details, and purge partial chunks."""
    logger.error(
        "ProcessingRun %s failed with [%s]: %s", run.id, error_code, error_message
    )
    try:
        with transaction.atomic():
            # Delete any partial chunks created during this run
            DocumentChunk.objects.filter(processing_run=run).delete()
            run.status = ProcessingStatus.FAILED
            run.is_active = False
            run.error_code = error_code
            run.error_message = error_message
            run.finished_at = timezone.now()
            run.save(
                update_fields=[
                    "status",
                    "is_active",
                    "error_code",
                    "error_message",
                    "finished_at",
                    "updated_at",
                ]
            )
    except Exception as save_exc:
        logger.exception(
            "Failed to record failure state on ProcessingRun %s: %s", run.id, save_exc
        )
