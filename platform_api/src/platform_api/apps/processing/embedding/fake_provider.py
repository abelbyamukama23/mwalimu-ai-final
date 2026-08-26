"""Deterministic in-memory fake embedding provider for unit and integration testing."""

from __future__ import annotations

import hashlib
import random

from django.conf import settings

from . import EmbeddingProvider
from .openai_provider import _l2_normalize


class FakeEmbeddingProvider(EmbeddingProvider):
    """Generates deterministic pseudo-embeddings for tests without network calls."""

    def __init__(
        self,
        model_id: str | None = None,
        embedding_version: str | None = None,
        dimensions: int | None = None,
        max_batch_size: int = 100,
    ) -> None:
        """Initialize the fake provider with configurable model metadata."""
        self.model_id = (
            model_id
            if model_id is not None
            else getattr(settings, "EMBEDDING_MODEL", "fake-embedding-model")
        )
        self.embedding_version = (
            embedding_version
            if embedding_version is not None
            else getattr(settings, "EMBEDDING_VERSION", "1")
        )
        self.dimensions = (
            dimensions
            if dimensions is not None
            else int(getattr(settings, "EMBEDDING_DIMENSIONS", 1536))
        )
        self.max_batch_size = max_batch_size
        self.call_count = 0
        self.embedded_texts: list[str] = []

    def _generate_vector(self, text: str) -> list[float]:
        """Generate a deterministic vector derived from the text's SHA-256 hash."""
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        # Seed RNG with the first 8 bytes of the digest
        seed = int.from_bytes(digest[:8], byteorder="big")
        rng = random.Random(seed)

        # Generate pseudo-random normal values
        raw = [rng.gauss(0.0, 1.0) for _ in range(self.dimensions)]
        return _l2_normalize(raw)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return deterministic vectors for each input text."""
        self.call_count += 1
        self.embedded_texts.extend(texts)
        return [self._generate_vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        """Return deterministic vector for query."""
        return self._generate_vector(text)
