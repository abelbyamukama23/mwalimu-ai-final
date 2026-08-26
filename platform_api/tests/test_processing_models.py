"""Tests for ProcessingRun, DocumentChunk, and ChunkEmbedding data models."""

import uuid

import pytest
from django.db import IntegrityError

from platform_api.apps.libraries.models import Library
from platform_api.apps.processing.models import (
    ChunkEmbedding,
    DocumentChunk,
    ProcessingRun,
    ProcessingStatus,
)
from platform_api.apps.resources.models import Resource, ResourceStatus, ResourceType
from platform_api.apps.resources.object_key import generate_resource_object_key


@pytest.fixture
def resource_a(db, library_a: Library, user_a) -> Resource:
    """Create a sample Resource."""
    res_id = uuid.uuid4()
    return Resource.objects.create(
        id=res_id,
        library=library_a,
        name="Textbook.pdf",
        resource_type=ResourceType.PDF,
        original_filename="textbook.pdf",
        content_type="application/pdf",
        size=1024,
        object_key=generate_resource_object_key(library_a.pk, res_id),
        checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        status=ResourceStatus.READY,
        created_by=user_a,
    )


@pytest.mark.django_db
def test_processing_run_creation(resource_a: Resource) -> None:
    """A ProcessingRun can be created with expected default fields."""
    run = ProcessingRun.objects.create(
        resource=resource_a,
        library=resource_a.library,
        source_checksum=resource_a.checksum,
        pipeline_version="1",
        extractor_version="pypdf-5",
        chunker_version="1",
        embedding_model="text-embedding-3-small",
        embedding_version="1",
        embedding_dimensions=1536,
    )

    assert run.status == ProcessingStatus.QUEUED
    assert run.is_active is False
    assert run.attempt_count == 0
    assert run.library == resource_a.library


@pytest.mark.django_db
def test_processing_run_identity_uniqueness(resource_a: Resource) -> None:
    """Duplicate non-failed runs with identical identity are rejected by DB."""
    ProcessingRun.objects.create(
        resource=resource_a,
        library=resource_a.library,
        source_checksum=resource_a.checksum,
        pipeline_version="1",
        extractor_version="pypdf-5",
        chunker_version="1",
        embedding_model="text-embedding-3-small",
        embedding_version="1",
        embedding_dimensions=1536,
        status=ProcessingStatus.READY,
    )

    with pytest.raises(IntegrityError):
        ProcessingRun.objects.create(
            resource=resource_a,
            library=resource_a.library,
            source_checksum=resource_a.checksum,
            pipeline_version="1",
            extractor_version="pypdf-5",
            chunker_version="1",
            embedding_model="text-embedding-3-small",
            embedding_version="1",
            embedding_dimensions=1536,
            status=ProcessingStatus.READY,
        )


@pytest.mark.django_db
def test_processing_run_allows_multiple_failed_runs(resource_a: Resource) -> None:
    """Multiple failed runs with identical identity are allowed for audit/history."""
    run1 = ProcessingRun.objects.create(
        resource=resource_a,
        library=resource_a.library,
        source_checksum=resource_a.checksum,
        pipeline_version="1",
        extractor_version="pypdf-5",
        chunker_version="1",
        embedding_model="text-embedding-3-small",
        embedding_version="1",
        embedding_dimensions=1536,
        status=ProcessingStatus.FAILED,
        error_code="EXTRACTION_FAILED",
    )

    run2 = ProcessingRun.objects.create(
        resource=resource_a,
        library=resource_a.library,
        source_checksum=resource_a.checksum,
        pipeline_version="1",
        extractor_version="pypdf-5",
        chunker_version="1",
        embedding_model="text-embedding-3-small",
        embedding_version="1",
        embedding_dimensions=1536,
        status=ProcessingStatus.FAILED,
        error_code="EXTRACTION_FAILED",
    )

    assert run1.id != run2.id
    assert ProcessingRun.objects.filter(resource=resource_a).count() == 2


@pytest.mark.django_db
def test_processing_run_active_uniqueness(resource_a: Resource) -> None:
    """Only one processing run can be active per resource."""
    ProcessingRun.objects.create(
        resource=resource_a,
        library=resource_a.library,
        source_checksum=resource_a.checksum,
        pipeline_version="1",
        extractor_version="pypdf-5",
        chunker_version="1",
        embedding_model="text-embedding-3-small",
        embedding_version="1",
        embedding_dimensions=1536,
        status=ProcessingStatus.READY,
        is_active=True,
    )

    with pytest.raises(IntegrityError):
        ProcessingRun.objects.create(
            resource=resource_a,
            library=resource_a.library,
            source_checksum=resource_a.checksum,
            pipeline_version="2",
            extractor_version="pypdf-5",
            chunker_version="1",
            embedding_model="text-embedding-3-small",
            embedding_version="1",
            embedding_dimensions=1536,
            status=ProcessingStatus.READY,
            is_active=True,
        )


@pytest.mark.django_db
def test_document_chunk_sequence_uniqueness(resource_a: Resource) -> None:
    """Chunk sequence must be unique per processing run."""
    run = ProcessingRun.objects.create(
        resource=resource_a,
        library=resource_a.library,
        source_checksum=resource_a.checksum,
        pipeline_version="1",
        extractor_version="pypdf-5",
        chunker_version="1",
        embedding_model="text-embedding-3-small",
        embedding_version="1",
        embedding_dimensions=1536,
    )

    DocumentChunk.objects.create(
        processing_run=run,
        resource=resource_a,
        library=resource_a.library,
        sequence=0,
        text="First chunk text.",
        token_count=4,
        char_start=0,
        char_end=17,
        page_start=1,
        page_end=1,
        section="Intro",
        content_sha256="abc",
    )

    with pytest.raises(IntegrityError):
        DocumentChunk.objects.create(
            processing_run=run,
            resource=resource_a,
            library=resource_a.library,
            sequence=0,
            text="Duplicate sequence chunk.",
            token_count=4,
            char_start=0,
            char_end=24,
            page_start=1,
            page_end=1,
            section="Intro",
            content_sha256="def",
        )


@pytest.mark.django_db
def test_chunk_embedding_versioned_identity(resource_a: Resource) -> None:
    """A DocumentChunk can accumulate multiple versioned embeddings."""
    run = ProcessingRun.objects.create(
        resource=resource_a,
        library=resource_a.library,
        source_checksum=resource_a.checksum,
        pipeline_version="1",
        extractor_version="pypdf-5",
        chunker_version="1",
        embedding_model="text-embedding-3-small",
        embedding_version="1",
        embedding_dimensions=1536,
    )

    chunk = DocumentChunk.objects.create(
        processing_run=run,
        resource=resource_a,
        library=resource_a.library,
        sequence=0,
        text="Sample chunk for embedding.",
        token_count=6,
        char_start=0,
        char_end=27,
        content_sha256="123",
    )

    vec = [0.0] * 1536
    vec[0] = 1.0

    # Generation 1
    emb1 = ChunkEmbedding.objects.create(
        chunk=chunk,
        vector=vec,
        embedding_model="text-embedding-3-small",
        embedding_version="1",
        dimensions=1536,
    )

    # Generation 2 (same chunk, new embedding_version)
    emb2 = ChunkEmbedding.objects.create(
        chunk=chunk,
        vector=vec,
        embedding_model="text-embedding-3-small",
        embedding_version="2",
        dimensions=1536,
    )

    assert chunk.embeddings.count() == 2
    assert emb1.id != emb2.id

    # Duplicate of generation 1 should raise IntegrityError
    with pytest.raises(IntegrityError):
        ChunkEmbedding.objects.create(
            chunk=chunk,
            vector=vec,
            embedding_model="text-embedding-3-small",
            embedding_version="1",
            dimensions=1536,
        )


@pytest.mark.django_db
def test_resource_cascade_deletion(resource_a: Resource) -> None:
    """Deleting a Resource cascades to its ProcessingRuns, Chunks, and Embeddings."""
    run = ProcessingRun.objects.create(
        resource=resource_a,
        library=resource_a.library,
        source_checksum=resource_a.checksum,
        pipeline_version="1",
        extractor_version="pypdf-5",
        chunker_version="1",
        embedding_model="text-embedding-3-small",
        embedding_version="1",
        embedding_dimensions=1536,
    )

    chunk = DocumentChunk.objects.create(
        processing_run=run,
        resource=resource_a,
        library=resource_a.library,
        sequence=0,
        text="Cascade text.",
        token_count=2,
        char_start=0,
        char_end=13,
        content_sha256="casc",
    )

    ChunkEmbedding.objects.create(
        chunk=chunk,
        vector=[0.0] * 1536,
        embedding_model="text-embedding-3-small",
        embedding_version="1",
        dimensions=1536,
    )

    resource_a.delete()

    assert ProcessingRun.objects.filter(pk=run.pk).count() == 0
    assert DocumentChunk.objects.filter(pk=chunk.pk).count() == 0
    assert ChunkEmbedding.objects.count() == 0
