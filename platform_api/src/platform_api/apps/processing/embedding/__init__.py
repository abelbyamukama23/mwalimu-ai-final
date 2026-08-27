"""Embedding provider abstraction protocol and provider loader."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from django.conf import settings
from django.utils.module_loading import import_string


class EmbeddingError(Exception):
    """Raised when an embedding provider fails to generate vector embeddings."""


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol defining the boundary for embedding generation backends."""

    model_id: str
    embedding_version: str
    dimensions: int
    max_batch_size: int

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate normalized vector embeddings for a list of document chunk texts."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Generate a normalized vector embedding for a single search query."""
        ...


def get_embedding_provider() -> EmbeddingProvider:
    """Instantiate and return the configured EmbeddingProvider from Django settings."""
    backend_path = getattr(
        settings,
        "EMBEDDING_PROVIDER_BACKEND",
        "platform_api.apps.processing.embedding.openai_provider.OpenAICompatibleProvider",
    )
    if not getattr(settings, "EMBEDDING_API_KEY", "") and backend_path.endswith("OpenAICompatibleProvider"):
        backend_path = "platform_api.apps.processing.embedding.fake_provider.FakeEmbeddingProvider"
    cls = import_string(backend_path)
    instance = cls()
    return instance  # type: ignore[no-any-return]
