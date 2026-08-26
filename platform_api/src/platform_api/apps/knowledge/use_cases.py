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

from .contracts import RetrieverProtocol
from .dto import SearchRequestDTO, SearchResponseDTO
from .pgvector_retriever import PgVectorRetriever
from .policies import KnowledgeAuthorizationPolicy


class SearchKnowledgeUseCase:
    """Orchestrates the knowledge retrieval workflow.

    Workflow:
    1. Resolve server-authoritative effective scope.
    2. Short-circuit if scope is empty.
    3. Generate query vector using EmbeddingProvider.
    4. Execute scoped vector similarity query.
    5. Assemble response with complete provenance metadata.
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
                },
            )

        # 3. Generate query vector
        try:
            query_vector = self.embedder.embed_query(request_dto.query)
        except Exception as exc:
            raise EmbeddingError(f"Query embedding generation failed: {exc}") from exc

        # 4. Execute scoped retrieval
        results = self.retriever.retrieve(
            query_vector=query_vector,
            scope=scope,
            embedding_model=self.embedder.model_id,
            embedding_version=self.embedder.embedding_version,
            dimensions=self.embedder.dimensions,
            top_k=effective_top_k,
            similarity_threshold=request_dto.similarity_threshold,
            include_text=request_dto.include_text,
        )

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return SearchResponseDTO(
            query=request_dto.query,
            result_count=len(results),
            embedding_model=self.embedder.model_id,
            embedding_version=self.embedder.embedding_version,
            results=results,
            metadata={
                "search_time_ms": elapsed_ms,
                "libraries_searched": len(scope.authorized_library_ids),
                "embedding_dimensions": self.embedder.dimensions,
            },
        )
