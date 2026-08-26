"""Integration tests for processing pipeline and failure semantics."""

import uuid
from io import BytesIO

import pytest

from platform_api.apps.libraries.models import Library
from platform_api.apps.processing.models import (
    ChunkEmbedding,
    DocumentChunk,
    ProcessingStatus,
)
from platform_api.apps.processing.services import enqueue_processing
from platform_api.apps.processing.tasks import process_resource_run
from platform_api.apps.resources.checksum import sha256_checksum
from platform_api.apps.resources.models import Resource, ResourceStatus, ResourceType
from platform_api.apps.resources.object_key import generate_resource_object_key
from platform_api.apps.resources.storage import get_object_storage


@pytest.fixture
def txt_resource(db, library_a: Library, user_a, txt_bytes: bytes) -> Resource:
    """Create and upload a text resource into storage."""
    res_id = uuid.uuid4()
    key = generate_resource_object_key(library_a.pk, res_id)
    storage = get_object_storage()
    storage.upload(key, BytesIO(txt_bytes), "text/plain", len(txt_bytes))

    return Resource.objects.create(
        id=res_id,
        library=library_a,
        name="biology_notes.txt",
        resource_type=ResourceType.TXT,
        original_filename="biology_notes.txt",
        content_type="text/plain",
        size=len(txt_bytes),
        object_key=key,
        checksum=sha256_checksum(BytesIO(txt_bytes)),
        status=ResourceStatus.READY,
        created_by=user_a,
    )


@pytest.fixture
def docx_resource(db, library_a: Library, user_a, docx_bytes: bytes) -> Resource:
    """Create and upload a DOCX resource into storage."""
    res_id = uuid.uuid4()
    key = generate_resource_object_key(library_a.pk, res_id)
    storage = get_object_storage()
    storage.upload(
        key,
        BytesIO(docx_bytes),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        len(docx_bytes),
    )

    return Resource.objects.create(
        id=res_id,
        library=library_a,
        name="physics_notes.docx",
        resource_type=ResourceType.DOCX,
        original_filename="physics_notes.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size=len(docx_bytes),
        object_key=key,
        checksum=sha256_checksum(BytesIO(docx_bytes)),
        status=ResourceStatus.READY,
        created_by=user_a,
    )


@pytest.mark.django_db
def test_pipeline_txt_successful_run(txt_resource: Resource) -> None:
    """A TXT resource is processed, chunked, embedded, and activated successfully."""
    run = enqueue_processing(txt_resource)

    # In eager mode, task executes synchronously
    run.refresh_from_db()

    assert run.status == ProcessingStatus.READY
    assert run.is_active is True
    assert run.finished_at is not None
    assert run.chunks.count() >= 2

    for chunk in run.chunks.all():
        assert chunk.library_id == txt_resource.library_id
        assert chunk.resource_id == txt_resource.id
        assert chunk.embeddings.count() == 1
        emb = chunk.embeddings.first()
        assert emb is not None
        assert len(emb.vector) == 1536


@pytest.mark.django_db
def test_pipeline_docx_successful_run(docx_resource: Resource) -> None:
    """A DOCX resource is processed, extracting headings and activating successfully."""
    run = enqueue_processing(docx_resource)
    run.refresh_from_db()

    assert run.status == ProcessingStatus.READY
    assert run.is_active is True
    assert run.chunks.count() >= 2

    headings = {c.section for c in run.chunks.all() if c.section}
    assert (
        "Chapter 1: Quantum Physics" in headings
        or "Chapter 2: Thermodynamics" in headings
    )


@pytest.mark.django_db
def test_pipeline_idempotency_duplicate_delivery(txt_resource: Resource) -> None:
    """Duplicate task delivery is safe and does not duplicate chunks."""
    run = enqueue_processing(txt_resource)
    run.refresh_from_db()
    initial_chunks_count = DocumentChunk.objects.filter(processing_run=run).count()
    initial_embeddings_count = ChunkEmbedding.objects.filter(
        chunk__processing_run=run
    ).count()

    # Re-deliver the same task
    process_resource_run(str(run.id))

    run.refresh_from_db()
    assert run.status == ProcessingStatus.READY
    assert (
        DocumentChunk.objects.filter(processing_run=run).count() == initial_chunks_count
    )
    assert (
        ChunkEmbedding.objects.filter(chunk__processing_run=run).count()
        == initial_embeddings_count
    )


@pytest.mark.django_db
def test_pipeline_reprocessing_atomic_activation(txt_resource: Resource) -> None:
    """Reprocessing creates a new run and atomically swaps is_active."""
    run1 = enqueue_processing(txt_resource, pipeline_version="1")
    run1.refresh_from_db()
    assert run1.is_active is True

    # Reprocess with pipeline_version="2"
    run2 = enqueue_processing(txt_resource, pipeline_version="2")
    run2.refresh_from_db()

    assert run2.id != run1.id
    assert run2.is_active is True
    assert run2.status == ProcessingStatus.READY

    run1.refresh_from_db()
    assert run1.is_active is False
    assert run1.status == ProcessingStatus.READY
    # Old chunks and embeddings are preserved for rollback
    assert run1.chunks.count() > 0


@pytest.mark.django_db
def test_pipeline_empty_extraction_fails(library_a: Library, user_a) -> None:
    """Whitespace-only resource fails with error_code=EMPTY_EXTRACTION."""
    empty_content = b"   \n\n  \t  \n  "
    res_id = uuid.uuid4()
    key = generate_resource_object_key(library_a.pk, res_id)
    storage = get_object_storage()
    storage.upload(key, BytesIO(empty_content), "text/plain", len(empty_content))

    empty_resource = Resource.objects.create(
        id=res_id,
        library=library_a,
        name="empty.txt",
        resource_type=ResourceType.TXT,
        original_filename="empty.txt",
        content_type="text/plain",
        size=len(empty_content),
        object_key=key,
        checksum=sha256_checksum(BytesIO(empty_content)),
        status=ResourceStatus.READY,
        created_by=user_a,
    )

    run = enqueue_processing(empty_resource)
    run.refresh_from_db()

    assert run.status == ProcessingStatus.FAILED
    assert run.is_active is False
    assert run.error_code == "EMPTY_EXTRACTION"
    assert run.chunks.count() == 0


@pytest.mark.django_db
def test_pipeline_corrupt_file_fails(library_a: Library, user_a) -> None:
    """A corrupt binary fails with status=FAILED and error_code=EXTRACTION_FAILED."""
    bad_docx = b"PK\x03\x04corrupted binary that is not a valid zip docx"
    res_id = uuid.uuid4()
    key = generate_resource_object_key(library_a.pk, res_id)
    storage = get_object_storage()
    storage.upload(
        key,
        BytesIO(bad_docx),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        len(bad_docx),
    )

    corrupt_resource = Resource.objects.create(
        id=res_id,
        library=library_a,
        name="corrupt.docx",
        resource_type=ResourceType.DOCX,
        original_filename="corrupt.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size=len(bad_docx),
        object_key=key,
        checksum=sha256_checksum(BytesIO(bad_docx)),
        status=ResourceStatus.READY,
        created_by=user_a,
    )

    run = enqueue_processing(corrupt_resource)
    run.refresh_from_db()

    assert run.status == ProcessingStatus.FAILED
    assert run.is_active is False
    assert run.error_code == "EXTRACTION_FAILED"
    assert run.chunks.count() == 0
