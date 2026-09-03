"""Contracts and protocols for the Knowledge Gateway."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from .dto import SearchResultItemDTO
from .policies import EffectiveRetrievalScope


class RetrieverProtocol(Protocol):
    """Protocol for vector similarity retrieval implementations."""

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
        query_intent: Any = None,
    ) -> list[SearchResultItemDTO]:

        """Execute vector similarity search within the effective scope.

        Args:
            query_vector: Normalized dense query vector.
            scope: Immutable effective retrieval scope.
            embedding_model: Expected embedding model identifier.
            embedding_version: Expected embedding generation version.
            dimensions: Expected vector dimensions.
            top_k: Maximum candidate count.
            similarity_threshold: Optional minimum cosine similarity filter.
            include_text: Whether to populate chunk text in result items.
            target_structure_node_ids: Optional structure node IDs to restrict candidate chunks.
            query_text: Raw query text for hybrid lexical relevance scoring.
            target_page_numbers: Optional candidate physical page numbers to target chunks.

        Returns:
            List of scored SearchResultItemDTO objects ordered by descending similarity.
        """
        ...



