"""Application use case for knowledge retrieval."""

from __future__ import annotations

import time

from django.conf import settings

from platform_api.apps.processing.embedding import (
    EmbeddingError,
    EmbeddingProvider,
    get_embedding_provider,
)
from platform_api.apps.users.models import User

from .citation_assembly import (
    extract_answer_spans,
    resolve_chunk_citations,
    synthesize_derivation_cluster,
)
from .concept_normalization import extract_query_concepts
from .context_expansion import expand_retrieval_context
from .contracts import RetrieverProtocol
from .dto import SearchRequestDTO, SearchResponseDTO, SearchResultItemDTO
from .evidence_quality import evaluate_chunk_evidence, evaluate_cluster_evidence
from .index_search import find_candidate_index_pages
from .pgvector_retriever import PgVectorRetriever
from .policies import EffectiveRetrievalScope, KnowledgeAuthorizationPolicy
from .query_intent import QueryIntent, detect_query_intent
from .resource_search import find_candidate_resources
from .structure_search import find_candidate_structure_nodes






class SearchKnowledgeUseCase:
    """Orchestrates the knowledge retrieval workflow with hierarchical navigation and context expansion.

    Workflow:
    1. Resolve server-authoritative effective scope.
    2. Short-circuit if scope is empty.
    3. Match query concepts against authorized DocumentStructureNodes (TOC).
    4. Match query concepts against authorized BookIndexEntry back-of-book indexes.
    5. Generate query vector using EmbeddingProvider.
    6. Execute scoped hybrid vector + lexical retrieval with TOC & index guidance.
    7. Expand core evidence within bounded structural context (sequence ± 1).
    8. Assemble response with complete provenance metadata and retrieval strategy.
    """

    def __init__(
        self,
        policy: KnowledgeAuthorizationPolicy | None = None,
        retriever: RetrieverProtocol | None = None,
        embedder: EmbeddingProvider | None = None,
    ) -> None:
        self.policy = policy or KnowledgeAuthorizationPolicy()
        self.retriever = retriever or PgVectorRetriever()
        self.embedder = embedder or get_embedding_provider()

    def execute(
        self,
        user: User,
        request_dto: SearchRequestDTO,
        scope_type: str | None = None,
    ) -> SearchResponseDTO:
        """Execute the search workflow.

        Args:
            user: Authenticated user (execution identity).
            request_dto: Validated search request.
            scope_type: Authoritative knowledge scope decoded from the delegated
                execution token ("relevant" | "my" | "institution" | "public").
        """
        start_time = time.perf_counter()

        # 1. Resolve server-authoritative scope
        scope = self.policy.resolve(
            user=user,
            requested_library_ids=request_dto.library_ids,
            requested_resource_ids=request_dto.resource_ids,
            scope_type=scope_type,
        )

        # 1b. Apply Academic Context targeting within authorized boundary
        from .academic_context import (
            AcademicContextSummary,
            filter_libraries_by_academic_context,
            resolve_academic_context,
        )

        academic_ctx = resolve_academic_context(
            user, institution_id=request_dto.institution_id
        )
        if request_dto.academic_unit_id:
            academic_ctx = AcademicContextSummary(
                institution_id=request_dto.institution_id or academic_ctx.institution_id,
                role=academic_ctx.role,
                academic_unit_ids=frozenset([request_dto.academic_unit_id]),
                is_administrator=academic_ctx.is_administrator,
            )

        if academic_ctx.has_academic_context and not scope.is_empty:
            targeted_lib_ids = filter_libraries_by_academic_context(
                authorized_library_ids=scope.authorized_library_ids,
                academic_context=academic_ctx,
            )
            if targeted_lib_ids:
                scope = EffectiveRetrievalScope(
                    authorized_library_ids=targeted_lib_ids,
                    authorized_resource_ids=scope.authorized_resource_ids,
                )

        max_top_k = int(getattr(settings, "KNOWLEDGE_GATEWAY_MAX_TOP_K", 50))
        effective_top_k = max(1, min(request_dto.top_k, max_top_k))

        # 2. Short-circuit if scope is empty
        if scope.is_empty:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return SearchResponseDTO(
                query=request_dto.query,
                result_count=0,
                embedding_model=self.embedder.model_id,
                embedding_version=self.embedder.embedding_version,
                results=[],
                metadata={
                    "search_time_ms": elapsed_ms,
                    "libraries_searched": 0,
                    "embedding_dimensions": self.embedder.dimensions,
                    "retrieval_strategy": "empty_scope",
                },
            )

        # 3. Resource Prior: Disambiguate and prioritize resources within authorized scope
        resource_prior = find_candidate_resources(
            query=request_dto.query,
            scope=scope,
        )
        if resource_prior.is_scope_restricted and resource_prior.prioritized_resource_ids:
            nav_scope = EffectiveRetrievalScope(
                authorized_library_ids=scope.authorized_library_ids,
                authorized_resource_ids=frozenset(resource_prior.prioritized_resource_ids),
            )
        else:
            nav_scope = scope

        # 4. Query Intent Recognition: Classify conceptual intent of query
        intent_result = detect_query_intent(request_dto.query)

        # 5. Structural navigation: Match query concepts against prioritized document hierarchy (TOC)
        candidate_structure_node_ids = find_candidate_structure_nodes(
            query=request_dto.query,
            scope=nav_scope,
        )

        # 6. Book Index Lookup: Match query concepts against prioritized back-of-book subject indexes
        candidate_page_numbers = find_candidate_index_pages(
            query=request_dto.query,
            scope=nav_scope,
        )

        # Determine retrieval strategy metadata
        if candidate_page_numbers:
            strategy = "index_guided_hybrid"
        elif candidate_structure_node_ids:
            strategy = "structural_section"
        else:
            strategy = "global_hybrid"

        # 7. Generate query vector
        try:
            query_vector = self.embedder.embed_query(request_dto.query)
        except Exception as exc:
            raise EmbeddingError(f"Query embedding generation failed: {exc}") from exc

        # 8. Execute scoped hybrid retrieval with intent-guided ranking
        core_results = self.retriever.retrieve(
            query_vector=query_vector,
            scope=scope,
            embedding_model=self.embedder.model_id,
            embedding_version=self.embedder.embedding_version,
            dimensions=self.embedder.dimensions,
            top_k=effective_top_k,
            similarity_threshold=request_dto.similarity_threshold,
            include_text=request_dto.include_text,
            target_structure_node_ids=candidate_structure_node_ids or None,
            query_text=request_dto.query,
            target_page_numbers=candidate_page_numbers or None,
            query_intent=intent_result,
        )

        # 9. Bounded context expansion (adaptive sequence ± 1/2 within structural boundaries)
        context_window = int(getattr(settings, "KNOWLEDGE_CONTEXT_WINDOW", 1))
        expanded_results = expand_retrieval_context(
            core_results=core_results,
            scope=scope,
            context_window=context_window,
            query_intent=intent_result,
        )

        norm_concepts = extract_query_concepts(request_dto.query)
        is_procedural_expanded = (
            intent_result.intent in (QueryIntent.PROCEDURAL, QueryIntent.QUANTITATIVE)
            and any(
                any(m in r.text.lower() for m in ("step", "example", "solution", "calculate", "formula"))
                for r in core_results
            )
        )
        adaptive_window = 2 if is_procedural_expanded else context_window

        top_eq = 0.0
        if core_results:
            eq_obj = evaluate_chunk_evidence(
                chunk_text=core_results[0].text,
                section=core_results[0].provenance.section,
                query_text=request_dto.query,
                intent_result=intent_result,
            )
            top_eq = eq_obj.quality_score

        cluster_ready = False
        if expanded_results:
            cluster_eq = evaluate_cluster_evidence(
                cluster_items=expanded_results,
                query_text=request_dto.query,
                intent_result=intent_result,
            )
            cluster_ready = cluster_eq.is_answer_ready

        # 10. Stage 10: Citation resolution, span pinpointing, and derivation synthesis
        citations_map = resolve_chunk_citations(expanded_results, scope)
        enriched_results: list[SearchResultItemDTO] = []
        for item in expanded_results:
            spans = extract_answer_spans(
                chunk_text=item.text,
                query_text=request_dto.query,
                intent_result=intent_result,
            )
            item_citation = citations_map.get(item.chunk_id)
            enriched_results.append(
                SearchResultItemDTO(
                    chunk_id=item.chunk_id,
                    score=item.score,
                    text=item.text,
                    provenance=item.provenance,
                    citation=item_citation,
                    answer_spans=spans if spans else None,
                )
            )

        synthesized_derivation_data = None
        if cluster_ready or is_procedural_expanded:
            cluster_obj = synthesize_derivation_cluster(
                cluster_items=enriched_results,
                query_text=request_dto.query,
                intent_result=intent_result,
                citations_map=citations_map,
            )
            if cluster_obj:
                synthesized_derivation_data = {
                    "core_chunk_id": str(cluster_obj.core_chunk_id),
                    "is_complete_derivation": cluster_obj.is_complete_derivation,
                    "formatted_citation": cluster_obj.formatted_citation,
                    "derivation_steps": cluster_obj.derivation_steps,
                }

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return SearchResponseDTO(
            query=request_dto.query,
            result_count=len(enriched_results),
            embedding_model=self.embedder.model_id,
            embedding_version=self.embedder.embedding_version,
            results=enriched_results,
            metadata={
                "search_time_ms": elapsed_ms,
                "libraries_searched": len(scope.authorized_library_ids),
                "embedding_dimensions": self.embedder.dimensions,
                "retrieval_strategy": strategy,
                "candidate_sections_matched": len(candidate_structure_node_ids),
                "candidate_pages_matched": len(candidate_page_numbers),
                "core_results_count": len(core_results),
                "expanded_results_count": len(expanded_results),
                "query_intent": (
                    intent_result.intent.value if intent_result.intent else None
                ),
                "query_intent_confidence": intent_result.confidence,
                "candidate_resources": [
                    str(r) for r in resource_prior.prioritized_resource_ids
                ],
                "resource_selection_confidence": resource_prior.confidence,
                "resource_scope_restricted": resource_prior.is_scope_restricted,
                "concept_normalization_applied": bool(
                    norm_concepts.canonical_concepts
                    or norm_concepts.aliases_applied
                    or len(norm_concepts.normalized_terms) > 1
                ),
                "normalized_concepts": (
                    list(norm_concepts.canonical_concepts)
                    if norm_concepts.canonical_concepts
                    else list(norm_concepts.normalized_terms[:5])
                ),
                "aliases_applied": [
                    {"alias": a[0], "canonical": a[1]}
                    for a in norm_concepts.aliases_applied
                ],
                "adaptive_context_window": adaptive_window,
                "evidence_quality_applied": True,
                "evidence_quality_version": "stage9",
                "top_evidence_quality": top_eq,
                "answer_ready_cluster": cluster_ready,
                "citation_resolution_applied": True,
                "synthesized_derivation": synthesized_derivation_data,
                "academic_context_applied": academic_ctx.has_academic_context,
                "academic_units_scoped": [str(u) for u in academic_ctx.academic_unit_ids],
            },
        )







