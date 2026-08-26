"""Indexing and scoped vector similarity search services.

Enforces:
- Transactional chunk and embedding persistence.
- Atomic ProcessingRun activation with history preservation.
- Authorization-before-vector-search invariant.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from django.db import connection, transaction
from django.utils import timezone

from .chunker import ChunkResult
from .models import ChunkEmbedding, DocumentChunk, ProcessingRun, ProcessingStatus


@dataclass(frozen=True)
class SearchResult:
    """A scored vector similarity search result with complete provenance."""

    chunk_id: uuid.UUID
    text: str
    page_start: int | None
    page_end: int | None
    section: str | None
    sequence: int
    resource_id: uuid.UUID
    resource_name: str
    library_id: uuid.UUID
    distance: float


@transaction.atomic
def write_chunks_and_embeddings(
    run: ProcessingRun,
    chunks: Sequence[ChunkResult],
    vectors: Sequence[Sequence[float]],
) -> list[DocumentChunk]:
    """Persist chunks and embeddings transactionally for a processing run.

    Args:
        run: The target ProcessingRun.
        chunks: Sequence of ChunkResult instances.
        vectors: Corresponding normalized vector embeddings.

    Returns:
        List of created or updated DocumentChunk model instances.

    Raises:
        ValueError: If chunk count and vector count do not match.
    """
    if len(chunks) != len(vectors):
        raise ValueError(
            f"Mismatched chunk count ({len(chunks)}) and vector count ({len(vectors)})"
        )

    # Delete any existing incomplete chunks for this run (for safe retry idempotency)
    DocumentChunk.objects.filter(processing_run=run).delete()

    created_chunks: list[DocumentChunk] = []
    chunk_embedding_pairs: list[tuple[DocumentChunk, Sequence[float]]] = []

    for chunk_res, vector in zip(chunks, vectors, strict=True):
        chunk_obj = DocumentChunk(
            processing_run=run,
            resource=run.resource,
            library=run.library,
            sequence=chunk_res.sequence,
            text=chunk_res.text,
            token_count=chunk_res.token_count,
            char_start=chunk_res.char_start,
            char_end=chunk_res.char_end,
            page_start=chunk_res.page_start,
            page_end=chunk_res.page_end,
            section=chunk_res.section,
            content_sha256=chunk_res.content_sha256,
        )
        created_chunks.append(chunk_obj)
        chunk_embedding_pairs.append((chunk_obj, vector))

    # Bulk create document chunks
    DocumentChunk.objects.bulk_create(created_chunks)

    # Create chunk embeddings
    embeddings: list[ChunkEmbedding] = []
    for chunk_obj, vector in chunk_embedding_pairs:
        embedding_obj = ChunkEmbedding(
            chunk=chunk_obj,
            vector=list(vector),
            embedding_model=run.embedding_model,
            embedding_version=run.embedding_version,
            dimensions=run.embedding_dimensions,
        )
        embeddings.append(embedding_obj)

    ChunkEmbedding.objects.bulk_create(embeddings)
    return created_chunks


@transaction.atomic
def activate_run(run: ProcessingRun) -> None:
    """Atomically activate a completed run and deactivate prior active runs."""
    # Deactivate any currently active runs for this resource
    ProcessingRun.objects.filter(
        resource=run.resource,
        is_active=True,
    ).exclude(pk=run.pk).update(is_active=False)

    # Activate the target run
    run.is_active = True
    run.status = ProcessingStatus.READY
    run.finished_at = timezone.now()
    run.error_code = None
    run.error_message = None
    run.save(
        update_fields=[
            "is_active",
            "status",
            "finished_at",
            "error_code",
            "error_message",
            "updated_at",
        ]
    )


def scoped_similarity_search(
    query_vector: Sequence[float],
    authorized_library_ids: Sequence[uuid.UUID],
    authorized_resource_ids: Sequence[uuid.UUID] | None = None,
    embedding_model: str | None = None,
    embedding_version: str | None = None,
    dimensions: int | None = None,
    top_k: int = 10,
) -> list[SearchResult]:
    """Execute scoped vector search with authorization-before-search enforcement.

    CRITICAL INVARIANT:
    Unauthorized library/resource vectors never enter the candidate set.
    Scoping happens through authorized_library_ids in the WHERE clause,
    not by filtering results post-search.

    Args:
        query_vector: Dense vector for query.
        authorized_library_ids: Sequence of library UUIDs authorized to search.
        authorized_resource_ids: Optional resource UUIDs to scope search.
        embedding_model: Optional embedding model guard.
        embedding_version: Optional embedding version guard.
        dimensions: Optional dimensions guard.
        top_k: Maximum number of nearest neighbor results to return.

    Returns:
        List of SearchResult objects ordered by ascending cosine distance.
    """
    if not authorized_library_ids:
        # Authorization check: zero authorized libraries yields zero results immediately
        return []

    lib_ids_str = [str(lid) for lid in authorized_library_ids]
    res_ids_str = (
        [str(rid) for rid in authorized_resource_ids]
        if authorized_resource_ids is not None
        else None
    )

    # Convert query vector into pgvector string format "[x1, x2, ...]"
    vector_str = "[" + ",".join(str(float(x)) for x in query_vector) + "]"

    sql = """
    SELECT
        c.id AS chunk_id,
        c.text AS chunk_text,
        c.page_start,
        c.page_end,
        c.section,
        c.sequence,
        r.id AS resource_id,
        r.name AS resource_name,
        c.library_id,
        (e.vector <=> %s::vector) AS distance
    FROM chunk_embedding e
    JOIN document_chunk c ON c.id = e.chunk_id
    JOIN processing_run pr ON pr.id = c.processing_run_id
    JOIN resources_resource r ON r.id = c.resource_id
    WHERE c.library_id = ANY(%s::uuid[])
      AND (%s::uuid[] IS NULL OR c.resource_id = ANY(%s::uuid[]))
      AND pr.is_active IS TRUE
      AND (%s::text IS NULL OR e.embedding_model = %s::text)
      AND (%s::text IS NULL OR e.embedding_version = %s::text)
      AND (%s::integer IS NULL OR e.dimensions = %s::integer)
      AND e.embedding_model = pr.embedding_model
      AND e.embedding_version = pr.embedding_version
      AND e.dimensions = pr.embedding_dimensions
    ORDER BY e.vector <=> %s::vector
    LIMIT %s;
    """

    params = [
        vector_str,
        lib_ids_str,
        res_ids_str,
        res_ids_str,
        embedding_model,
        embedding_model,
        embedding_version,
        embedding_version,
        dimensions,
        dimensions,
        vector_str,
        top_k,
    ]

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()

    results: list[SearchResult] = []
    for row in rows:
        results.append(
            SearchResult(
                chunk_id=uuid.UUID(str(row[0])),
                text=str(row[1]),
                page_start=int(row[2]) if row[2] is not None else None,
                page_end=int(row[3]) if row[3] is not None else None,
                section=str(row[4]) if row[4] is not None else None,
                sequence=int(row[5]),
                resource_id=uuid.UUID(str(row[6])),
                resource_name=str(row[7]),
                library_id=uuid.UUID(str(row[8])),
                distance=float(row[9]),
            )
        )

    return results
