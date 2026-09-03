"""Tests for Knowledge Retrieval application use case."""

import uuid
from collections.abc import Sequence
from typing import Any

import pytest

from platform_api.apps.knowledge.dto import (
    ProvenanceDTO,
    SearchRequestDTO,
    SearchResultItemDTO,
)
from platform_api.apps.knowledge.policies import (
    EffectiveRetrievalScope,
    KnowledgeAuthorizationPolicy,
)
from platform_api.apps.knowledge.use_cases import SearchKnowledgeUseCase
from platform_api.apps.processing.embedding import EmbeddingError
from platform_api.apps.processing.embedding.fake_provider import FakeEmbeddingProvider
from platform_api.apps.users.models import User


class FakePolicy(KnowledgeAuthorizationPolicy):
    """Fake policy returning predefined EffectiveRetrievalScope."""

    def __init__(self, scope: EffectiveRetrievalScope) -> None:
        self._scope = scope

    def resolve(
        self,
        user: User,
        requested_library_ids: Sequence[uuid.UUID] | None = None,
        requested_resource_ids: Sequence[uuid.UUID] | None = None,
        scope_type: str | None = None,
    ) -> EffectiveRetrievalScope:
        return self._scope


class FakeRetriever:
    """Fake retriever recording calls and returning predefined results."""

    def __init__(self, results: list[SearchResultItemDTO] | None = None) -> None:
        self.results = results or []
        self.call_count = 0
        self.last_scope: EffectiveRetrievalScope | None = None
        self.last_top_k: int | None = None

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
        **kwargs: Any,
    ) -> list[SearchResultItemDTO]:


        self.call_count += 1
        self.last_scope = scope
        self.last_top_k = top_k
        self.last_target_nodes = target_structure_node_ids
        self.last_query_text = query_text
        self.last_target_pages = target_page_numbers
        return self.results




class ErrorEmbeddingProvider(FakeEmbeddingProvider):
    """Embedding provider that raises an error on query embedding."""

    def embed_query(self, text: str) -> list[float]:
        raise RuntimeError("Provider connection failed")


@pytest.fixture
def mock_user() -> User:
    """Return a mock user."""
    return User(id=uuid.uuid4(), email="tester@example.com")


def test_use_case_empty_scope_short_circuits(mock_user: User) -> None:
    """Empty scope returns result_count=0 without calling embedder or retriever."""
    empty_scope = EffectiveRetrievalScope(frozenset(), frozenset())
    policy = FakePolicy(empty_scope)
    retriever = FakeRetriever()
    embedder = FakeEmbeddingProvider(dimensions=1536)

    use_case = SearchKnowledgeUseCase(
        policy=policy, retriever=retriever, embedder=embedder
    )
    request_dto = SearchRequestDTO(query="test query")

    response = use_case.execute(user=mock_user, request_dto=request_dto)

    assert response.result_count == 0
    assert response.results == []
    assert retriever.call_count == 0
    assert embedder.call_count == 0


def test_use_case_clamps_top_k(mock_user: User, settings: Any) -> None:
    """top_k is clamped to settings.KNOWLEDGE_GATEWAY_MAX_TOP_K."""
    settings.KNOWLEDGE_GATEWAY_MAX_TOP_K = 50

    active_scope = EffectiveRetrievalScope(frozenset([uuid.uuid4()]), None)
    policy = FakePolicy(active_scope)
    retriever = FakeRetriever()
    embedder = FakeEmbeddingProvider(dimensions=1536)

    use_case = SearchKnowledgeUseCase(
        policy=policy, retriever=retriever, embedder=embedder
    )

    # Request top_k = 100 -> should clamp to 50
    request_dto = SearchRequestDTO(query="test query", top_k=100)
    use_case.execute(user=mock_user, request_dto=request_dto)

    assert retriever.last_top_k == 50


def test_use_case_wraps_embedding_failure(mock_user: User) -> None:
    """Embedding provider failure is raised as EmbeddingError."""
    active_scope = EffectiveRetrievalScope(frozenset([uuid.uuid4()]), None)
    policy = FakePolicy(active_scope)
    retriever = FakeRetriever()
    embedder = ErrorEmbeddingProvider(dimensions=1536)

    use_case = SearchKnowledgeUseCase(
        policy=policy, retriever=retriever, embedder=embedder
    )
    request_dto = SearchRequestDTO(query="test query")

    with pytest.raises(EmbeddingError, match="Query embedding generation failed"):
        use_case.execute(user=mock_user, request_dto=request_dto)


def test_use_case_returns_populated_search_response(mock_user: User) -> None:
    """Use case returns populated search response with search metadata."""
    lib_id = uuid.uuid4()
    active_scope = EffectiveRetrievalScope(frozenset([lib_id]), None)
    policy = FakePolicy(active_scope)

    fake_result = SearchResultItemDTO(
        chunk_id=uuid.uuid4(),
        score=0.92,
        text="Sample text content",
        provenance=ProvenanceDTO(
            resource_id=uuid.uuid4(),
            resource_name="Doc.pdf",
            library_id=lib_id,
            library_name="Main Lib",
            page_start=1,
            page_end=1,
            section="Intro",
            sequence=0,
            char_start=0,
            char_end=19,
            content_sha256="sha-123",
        ),
    )
    retriever = FakeRetriever(results=[fake_result])
    embedder = FakeEmbeddingProvider(dimensions=1536)

    use_case = SearchKnowledgeUseCase(
        policy=policy, retriever=retriever, embedder=embedder
    )
    request_dto = SearchRequestDTO(query="biology intro")

    response = use_case.execute(user=mock_user, request_dto=request_dto)

    assert response.result_count == 1
    assert response.results[0].chunk_id == fake_result.chunk_id
    assert response.results[0].score == fake_result.score
    assert response.results[0].provenance == fake_result.provenance
    assert response.metadata["libraries_searched"] == 1

    assert response.metadata["embedding_dimensions"] == 1536
    assert response.metadata["search_time_ms"] >= 0
