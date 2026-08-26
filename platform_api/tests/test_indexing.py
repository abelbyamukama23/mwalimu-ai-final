"""Tests for indexing services and scoped vector similarity search."""

import uuid

import pytest

from platform_api.apps.libraries.models import Library
from platform_api.apps.processing.chunker import ChunkResult
from platform_api.apps.processing.embedding.fake_provider import FakeEmbeddingProvider
from platform_api.apps.processing.indexing import (
    activate_run,
    scoped_similarity_search,
    write_chunks_and_embeddings,
)
from platform_api.apps.processing.models import (
    ChunkEmbedding,
    DocumentChunk,
    ProcessingRun,
    ProcessingStatus,
)
from platform_api.apps.resources.models import Resource, ResourceStatus, ResourceType
from platform_api.apps.resources.object_key import generate_resource_object_key


@pytest.fixture
def resource_lib_a(db, library_a: Library, user_a) -> Resource:
    """Resource in Library A."""
    res_id = uuid.uuid4()
    return Resource.objects.create(
        id=res_id,
        library=library_a,
        name="Physics Book",
        resource_type=ResourceType.PDF,
        original_filename="physics.pdf",
        content_type="application/pdf",
        size=2048,
        object_key=generate_resource_object_key(library_a.pk, res_id),
        checksum="hash-physics",
        status=ResourceStatus.READY,
        created_by=user_a,
    )


@pytest.fixture
def resource_lib_b(db, library_b: Library, user_b) -> Resource:
    """Resource in Library B."""
    res_id = uuid.uuid4()
    return Resource.objects.create(
        id=res_id,
        library=library_b,
        name="Chemistry Book",
        resource_type=ResourceType.PDF,
        original_filename="chem.pdf",
        content_type="application/pdf",
        size=2048,
        object_key=generate_resource_object_key(library_b.pk, res_id),
        checksum="hash-chem",
        status=ResourceStatus.READY,
        created_by=user_b,
    )


@pytest.mark.django_db
def test_write_chunks_and_embeddings(resource_lib_a: Resource) -> None:
    """write_chunks_and_embeddings persists DocumentChunk and ChunkEmbedding rows."""
    run = ProcessingRun.objects.create(
        resource=resource_lib_a,
        library=resource_lib_a.library,
        source_checksum=resource_lib_a.checksum,
        pipeline_version="1",
        extractor_version="pypdf-5",
        chunker_version="1",
        embedding_model="fake-embedding-model",
        embedding_version="1",
        embedding_dimensions=1536,
    )

    chunks = [
        ChunkResult(
            sequence=0,
            text="Quantum mechanics explores atomic behavior.",
            token_count=6,
            char_start=0,
            char_end=43,
            page_start=1,
            page_end=1,
            section="Quantum",
            content_sha256="sha-1",
        ),
        ChunkResult(
            sequence=1,
            text="Thermodynamics explores heat exchange.",
            token_count=5,
            char_start=45,
            char_end=83,
            page_start=2,
            page_end=2,
            section="Thermo",
            content_sha256="sha-2",
        ),
    ]

    provider = FakeEmbeddingProvider(dimensions=1536)
    vectors = provider.embed_texts([c.text for c in chunks])

    created = write_chunks_and_embeddings(run, chunks, vectors)

    assert len(created) == 2
    assert DocumentChunk.objects.filter(processing_run=run).count() == 2
    assert ChunkEmbedding.objects.filter(chunk__processing_run=run).count() == 2


@pytest.mark.django_db
def test_activate_run_atomic_swap(resource_lib_a: Resource) -> None:
    """activate_run promotes the new run to active and deactivates prior runs."""
    run1 = ProcessingRun.objects.create(
        resource=resource_lib_a,
        library=resource_lib_a.library,
        source_checksum=resource_lib_a.checksum,
        pipeline_version="1",
        extractor_version="pypdf-5",
        chunker_version="1",
        embedding_model="fake-embedding-model",
        embedding_version="1",
        embedding_dimensions=1536,
        status=ProcessingStatus.READY,
        is_active=True,
    )

    run2 = ProcessingRun.objects.create(
        resource=resource_lib_a,
        library=resource_lib_a.library,
        source_checksum=resource_lib_a.checksum,
        pipeline_version="2",
        extractor_version="pypdf-5",
        chunker_version="1",
        embedding_model="fake-embedding-model",
        embedding_version="1",
        embedding_dimensions=1536,
        status=ProcessingStatus.PROCESSING,
        is_active=False,
    )

    activate_run(run2)

    run1.refresh_from_db()
    run2.refresh_from_db()

    assert run1.is_active is False
    assert run2.is_active is True
    assert run2.status == ProcessingStatus.READY


@pytest.mark.django_db
def test_scoped_similarity_search_authorization_isolation(
    resource_lib_a: Resource,
    resource_lib_b: Resource,
) -> None:
    """CRITICAL INVARIANT: Scoped vector search strictly isolates library data."""
    provider = FakeEmbeddingProvider(dimensions=1536)

    # Setup Run in Library A
    run_a = ProcessingRun.objects.create(
        resource=resource_lib_a,
        library=resource_lib_a.library,
        source_checksum=resource_lib_a.checksum,
        pipeline_version="1",
        extractor_version="pypdf-5",
        chunker_version="1",
        embedding_model="fake-embedding-model",
        embedding_version="1",
        embedding_dimensions=1536,
    )
    chunks_a = [
        ChunkResult(
            sequence=0,
            text="Special relativity and general relativity by Einstein.",
            token_count=8,
            char_start=0,
            char_end=54,
            page_start=1,
            page_end=1,
            section="Relativity",
            content_sha256="sha-a",
        )
    ]
    write_chunks_and_embeddings(
        run_a, chunks_a, provider.embed_texts([c.text for c in chunks_a])
    )
    activate_run(run_a)

    # Setup Run in Library B
    run_b = ProcessingRun.objects.create(
        resource=resource_lib_b,
        library=resource_lib_b.library,
        source_checksum=resource_lib_b.checksum,
        pipeline_version="1",
        extractor_version="pypdf-5",
        chunker_version="1",
        embedding_model="fake-embedding-model",
        embedding_version="1",
        embedding_dimensions=1536,
    )
    chunks_b = [
        ChunkResult(
            sequence=0,
            text="Organic chemistry and molecular structures.",
            token_count=6,
            char_start=0,
            char_end=43,
            page_start=1,
            page_end=1,
            section="Organic",
            content_sha256="sha-b",
        )
    ]
    write_chunks_and_embeddings(
        run_b, chunks_b, provider.embed_texts([c.text for c in chunks_b])
    )
    activate_run(run_b)

    query_vec = provider.embed_query("Einstein relativity physics")

    # 1. Search authorized only for Library A -> returns only Library A results
    results_a = scoped_similarity_search(
        query_vector=query_vec,
        authorized_library_ids=[resource_lib_a.library.id],
        top_k=5,
    )
    assert len(results_a) == 1
    assert results_a[0].library_id == resource_lib_a.library.id
    assert results_a[0].resource_id == resource_lib_a.id
    assert "relativity" in results_a[0].text

    # 2. Search authorized only for Library B -> returns only Library B results
    results_b = scoped_similarity_search(
        query_vector=query_vec,
        authorized_library_ids=[resource_lib_b.library.id],
        top_k=5,
    )
    assert len(results_b) == 1
    assert results_b[0].library_id == resource_lib_b.library.id
    assert results_b[0].resource_id == resource_lib_b.id
    assert "chemistry" in results_b[0].text

    # 3. Empty authorized_library_ids -> returns empty list immediately
    results_empty = scoped_similarity_search(
        query_vector=query_vec,
        authorized_library_ids=[],
        top_k=5,
    )
    assert results_empty == []


@pytest.mark.django_db
def test_scoped_similarity_search_inactive_run_invisible(
    resource_lib_a: Resource,
) -> None:
    """Inactive processing runs are invisible to search queries."""
    provider = FakeEmbeddingProvider(dimensions=1536)

    run = ProcessingRun.objects.create(
        resource=resource_lib_a,
        library=resource_lib_a.library,
        source_checksum=resource_lib_a.checksum,
        pipeline_version="1",
        extractor_version="pypdf-5",
        chunker_version="1",
        embedding_model="fake-embedding-model",
        embedding_version="1",
        embedding_dimensions=1536,
        status=ProcessingStatus.PROCESSING,
        is_active=False,
    )
    chunks = [
        ChunkResult(
            sequence=0,
            text="Hidden inactive text that must not appear in search.",
            token_count=10,
            char_start=0,
            char_end=53,
            page_start=1,
            page_end=1,
            section="Hidden",
            content_sha256="sha-hidden",
        )
    ]
    write_chunks_and_embeddings(
        run, chunks, provider.embed_texts([c.text for c in chunks])
    )

    query_vec = provider.embed_query("Hidden inactive text")
    results = scoped_similarity_search(
        query_vector=query_vec,
        authorized_library_ids=[resource_lib_a.library.id],
    )

    assert len(results) == 0
