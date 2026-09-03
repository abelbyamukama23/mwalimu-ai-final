"""PgVector implementation of RetrieverProtocol with single-query SQL retrieval."""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence

from django.db import connection

from .contracts import RetrieverProtocol
from .dto import ProvenanceDTO, SearchResultItemDTO
from .evidence_quality import evaluate_chunk_evidence
from .policies import EffectiveRetrievalScope
from .query_intent import QueryIntentResult, compute_intent_bonus
from .structure_search import _tokenize


def _build_tsquery(query_text: str) -> str:
    """Build a sanitized OR-joined tsquery expression from query content tokens."""
    tokens = _tokenize(query_text)
    clean_tokens = [re.sub(r"[^a-zA-Z0-9]", "", t) for t in tokens if len(t) > 1]
    clean_tokens = [t for t in clean_tokens if t]
    if not clean_tokens:
        return ""
    return " | ".join(clean_tokens)


class PgVectorRetriever:
    """Executes single-query scoped hybrid (vector + lexical) search against PostgreSQL.

    Invariants:
    - Authorization in WHERE clause prior to scoring and sorting.
    - Active-run and READY status enforcement.
    - Generation guards on embedding model, version, and dimensions.
    - Returns all 14 provenance fields.
    - Calibrated scoring: CombinedScore = vector_weight * VectorScore + lexical_weight * NormalizedLexicalScore.
    """

    DEFAULT_VECTOR_WEIGHT: float = 0.65
    DEFAULT_LEXICAL_WEIGHT: float = 0.35

    def __init__(
        self,
        vector_weight: float | None = None,
        lexical_weight: float | None = None,
    ) -> None:
        self.vector_weight = (
            vector_weight
            if vector_weight is not None
            else self.DEFAULT_VECTOR_WEIGHT
        )
        self.lexical_weight = (
            lexical_weight
            if lexical_weight is not None
            else self.DEFAULT_LEXICAL_WEIGHT
        )

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
        target_structure_node_ids: Sequence[uuid.UUID] | None = None,
        query_text: str | None = None,
        target_page_numbers: Sequence[int] | None = None,
        query_intent: QueryIntentResult | None = None,
    ) -> list[SearchResultItemDTO]:

        """Execute single-query scoped vector similarity search with optional structure/page scoping and lexical scoring."""
        if scope.is_empty:
            return []

        lib_ids_str = [str(lid) for lid in scope.authorized_library_ids]
        res_ids_str = (
            [str(rid) for rid in scope.authorized_resource_ids]
            if scope.authorized_resource_ids is not None
            else None
        )
        node_ids_str = (
            [str(nid) for nid in target_structure_node_ids]
            if target_structure_node_ids is not None
            else None
        )
        pages_list = list(target_page_numbers) if target_page_numbers else None

        vector_str = "[" + ",".join(str(float(x)) for x in query_vector) + "]"
        tsquery_str = _build_tsquery(query_text or "")

        def _execute_query(
            target_nodes: list[str] | None,
            target_pages: list[int] | None,
            limit: int,
            exclude_chunk_ids: list[str] | None = None,
        ) -> list[SearchResultItemDTO]:
            fetch_limit = (
                max(limit * 2, limit + 5)
                if ((query_intent and query_intent.intent) or query_text)
                else limit
            )

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
                (e.vector <=> %s::vector) AS distance,
                (CASE WHEN %s != '' THEN ts_rank_cd(to_tsvector('english', c.text), to_tsquery('english', %s)) ELSE 0.0 END) AS lexical_rank
            FROM chunk_embedding e
            JOIN document_chunk c ON c.id = e.chunk_id
            JOIN processing_run pr ON pr.id = c.processing_run_id
            JOIN resources_resource r ON r.id = c.resource_id
            JOIN libraries_library l ON l.id = c.library_id
            WHERE c.library_id = ANY(%s::uuid[])
              AND (%s::uuid[] IS NULL OR c.resource_id = ANY(%s::uuid[]))
              AND (%s::uuid[] IS NULL OR c.structure_node_id = ANY(%s::uuid[]))
              AND (%s::integer[] IS NULL OR c.page_start = ANY(%s::integer[]) OR c.page_end = ANY(%s::integer[]))
              AND (%s::uuid[] IS NULL OR NOT (c.id = ANY(%s::uuid[])))
              AND pr.is_active IS TRUE
              AND pr.status = 'ready'
              AND e.embedding_model = %s::text
              AND e.embedding_version = %s::text
              AND e.dimensions = %s::integer
              AND e.embedding_model = pr.embedding_model
              AND e.embedding_version = pr.embedding_version
              AND e.dimensions = pr.embedding_dimensions
            ORDER BY (
                %s::float * (1.0 - (e.vector <=> %s::vector)) +
                %s::float * (
                    CASE WHEN %s != '' THEN
                        (10.0 * ts_rank_cd(to_tsvector('english', c.text), to_tsquery('english', %s))) /
                        (1.0 + 10.0 * ts_rank_cd(to_tsvector('english', c.text), to_tsquery('english', %s)))
                    ELSE 0.0 END
                )
            ) DESC
            LIMIT %s;
            """
            params = [
                vector_str,
                tsquery_str,
                tsquery_str,
                lib_ids_str,
                res_ids_str,
                res_ids_str,
                target_nodes,
                target_nodes,
                target_pages,
                target_pages,
                target_pages,
                exclude_chunk_ids,
                exclude_chunk_ids,
                embedding_model,
                embedding_version,
                dimensions,
                self.vector_weight,
                vector_str,
                self.lexical_weight,
                tsquery_str,
                tsquery_str,
                tsquery_str,
                fetch_limit,
            ]

            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()

            batch_results: list[SearchResultItemDTO] = []
            for row in rows:
                distance = float(row[13])
                raw_lexical = float(row[14]) if row[14] is not None else 0.0
                vector_score = max(0.0, min(1.0, 1.0 - distance))
                norm_lexical = (10.0 * raw_lexical) / (1.0 + 10.0 * raw_lexical)
                base_score = (
                    self.vector_weight * vector_score
                    + self.lexical_weight * norm_lexical
                )

                chunk_full_text = str(row[1])
                chunk_text = chunk_full_text if include_text else ""
                chunk_section = str(row[4]) if row[4] is not None else None
                intent_bonus = compute_intent_bonus(
                    chunk_text=chunk_full_text,
                    section=chunk_section,
                    query_text=query_text or "",
                    intent_result=query_intent,
                )
                evidence_quality = evaluate_chunk_evidence(
                    chunk_text=chunk_full_text,
                    section=chunk_section,
                    query_text=query_text or "",
                    intent_result=query_intent,
                )
                evidence_bonus = evidence_quality.evidence_bonus
                combined_score = round(
                    min(1.0, base_score + intent_bonus + evidence_bonus), 6
                )


                if (
                    similarity_threshold is not None
                    and combined_score < similarity_threshold
                ):
                    continue

                provenance = ProvenanceDTO(
                    resource_id=uuid.UUID(str(row[9])),
                    resource_name=str(row[10]),
                    library_id=uuid.UUID(str(row[11])),
                    library_name=str(row[12]),
                    page_start=int(row[2]) if row[2] is not None else None,
                    page_end=int(row[3]) if row[3] is not None else None,
                    section=chunk_section,
                    sequence=int(row[5]),
                    char_start=int(row[6]),
                    char_end=int(row[7]),
                    content_sha256=str(row[8]),
                )

                batch_results.append(
                    SearchResultItemDTO(
                        chunk_id=uuid.UUID(str(row[0])),
                        score=combined_score,
                        text=chunk_text,
                        provenance=provenance,
                    )
                )

            if fetch_limit > limit:
                batch_results.sort(key=lambda r: r.score, reverse=True)
                batch_results = batch_results[:limit]

            return batch_results


        # Cascade: Targeted -> Partial Backfill -> Global
        accumulated_results: list[SearchResultItemDTO] = []
        retrieved_ids: list[str] = []

        # 1. Level 1: Index candidate pages + Structure nodes
        if pages_list and node_ids_str:
            level1_results = _execute_query(
                target_nodes=node_ids_str,
                target_pages=pages_list,
                limit=top_k,
            )
            accumulated_results.extend(level1_results)
            retrieved_ids.extend(str(r.chunk_id) for r in level1_results)

        # 2. Level 2: Index candidate pages only
        if len(accumulated_results) < top_k and pages_list:
            remaining = top_k - len(accumulated_results)
            level2_results = _execute_query(
                target_nodes=None,
                target_pages=pages_list,
                limit=remaining,
                exclude_chunk_ids=retrieved_ids or None,
            )
            accumulated_results.extend(level2_results)
            retrieved_ids.extend(str(r.chunk_id) for r in level2_results)

        # 3. Level 3: Structure nodes only
        if len(accumulated_results) < top_k and node_ids_str:
            remaining = top_k - len(accumulated_results)
            level3_results = _execute_query(
                target_nodes=node_ids_str,
                target_pages=None,
                limit=remaining,
                exclude_chunk_ids=retrieved_ids or None,
            )
            accumulated_results.extend(level3_results)
            retrieved_ids.extend(str(r.chunk_id) for r in level3_results)

        # 4. Level 4: Global fallback backfill
        if len(accumulated_results) < top_k:
            remaining = top_k - len(accumulated_results)
            global_results = _execute_query(
                target_nodes=None,
                target_pages=None,
                limit=remaining,
                exclude_chunk_ids=retrieved_ids or None,
            )
            accumulated_results.extend(global_results)

        return accumulated_results



