"""PgVector implementation of RetrieverProtocol with single-query SQL retrieval."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from django.db import connection

from .dto import ProvenanceDTO, SearchResultItemDTO
from .policies import EffectiveRetrievalScope


class PgVectorRetriever:
    """Executes single-query scoped vector search against PostgreSQL + pgvector.

    Invariants:
    - Authorization in WHERE clause prior to distance sorting.
    - Active-run and READY status enforcement.
    - Generation guards on embedding model, version, and dimensions.
    - Returns all 14 provenance fields.
    """

    def retrieve(
        self,
        query_vector: Sequence[float],
        scope: EffectiveRetrievalScope,
        embedding_model: str,
        embedding_version: str,
        dimensions: int,
        top_k: int,
        similarity_threshold: float | None = None,
        include_text: bool = True,
    ) -> list[SearchResultItemDTO]:
        """Execute single-query scoped vector similarity search."""
        if scope.is_empty:
            return []

        lib_ids_str = [str(lid) for lid in scope.authorized_library_ids]
        res_ids_str = (
            [str(rid) for rid in scope.authorized_resource_ids]
            if scope.authorized_resource_ids is not None
            else None
        )

        vector_str = "[" + ",".join(str(float(x)) for x in query_vector) + "]"

        sql = """
        SELECT
            c.id AS chunk_id,
            c.text AS chunk_text,
            c.page_start,
            c.page_end,
            c.section,
            c.sequence,
            c.char_start,
            c.char_end,
            c.content_sha256,
            r.id AS resource_id,
            r.name AS resource_name,
            l.id AS library_id,
            l.name AS library_name,
            (e.vector <=> %s::vector) AS distance
        FROM chunk_embedding e
        JOIN document_chunk c ON c.id = e.chunk_id
        JOIN processing_run pr ON pr.id = c.processing_run_id
        JOIN resources_resource r ON r.id = c.resource_id
        JOIN libraries_library l ON l.id = c.library_id
        WHERE c.library_id = ANY(%s::uuid[])
          AND (%s::uuid[] IS NULL OR c.resource_id = ANY(%s::uuid[]))
          AND pr.is_active IS TRUE
          AND pr.status = 'ready'
          AND e.embedding_model = %s::text
          AND e.embedding_version = %s::text
          AND e.dimensions = %s::integer
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
            embedding_version,
            dimensions,
            vector_str,
            top_k,
        ]

        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        results: list[SearchResultItemDTO] = []
        for row in rows:
            distance = float(row[13])
            score = round(1.0 - distance, 6)

            # Post-query similarity threshold filtering
            if similarity_threshold is not None and score < similarity_threshold:
                continue

            chunk_text = str(row[1]) if include_text else ""

            provenance = ProvenanceDTO(
                resource_id=uuid.UUID(str(row[9])),
                resource_name=str(row[10]),
                library_id=uuid.UUID(str(row[11])),
                library_name=str(row[12]),
                page_start=int(row[2]) if row[2] is not None else None,
                page_end=int(row[3]) if row[3] is not None else None,
                section=str(row[4]) if row[4] is not None else None,
                sequence=int(row[5]),
                char_start=int(row[6]),
                char_end=int(row[7]),
                content_sha256=str(row[8]),
            )

            results.append(
                SearchResultItemDTO(
                    chunk_id=uuid.UUID(str(row[0])),
                    score=score,
                    text=chunk_text,
                    provenance=provenance,
                )
            )

        return results
