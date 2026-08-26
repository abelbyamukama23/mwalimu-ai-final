"""OpenAI-compatible HTTP embedding provider using httpx."""

from __future__ import annotations

import math
from typing import Any

import httpx
from django.conf import settings

from . import EmbeddingError, EmbeddingProvider


def _l2_normalize(vector: list[float]) -> list[float]:
    """Return L2-normalized vector."""
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0.0 or math.isclose(norm, 1.0, rel_tol=1e-5):
        return vector
    return [x / norm for x in vector]


class OpenAICompatibleProvider(EmbeddingProvider):
    """Embedding provider calling an OpenAI-compatible HTTP endpoint."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model_id: str | None = None,
        embedding_version: str | None = None,
        dimensions: int | None = None,
        max_batch_size: int = 100,
        timeout: float = 60.0,
    ) -> None:
        """Initialize provider with configuration from parameters or settings."""
        self.base_url = (
            base_url
            if base_url is not None
            else getattr(
                settings, "EMBEDDING_API_BASE_URL", "https://api.openai.com/v1"
            )
        ).rstrip("/")
        self.api_key = (
            api_key
            if api_key is not None
            else getattr(settings, "EMBEDDING_API_KEY", "")
        )
        self.model_id = (
            model_id
            if model_id is not None
            else getattr(settings, "EMBEDDING_MODEL", "text-embedding-3-small")
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
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings in batches for a list of texts."""
        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        endpoint = f"{self.base_url}/embeddings"

        with httpx.Client(timeout=self.timeout) as client:
            for i in range(0, len(texts), self.max_batch_size):
                batch = texts[i : i + self.max_batch_size]
                payload: dict[str, Any] = {
                    "model": self.model_id,
                    "input": batch,
                }
                # If dimensions are supported by provider
                if "text-embedding-3" in self.model_id:
                    payload["dimensions"] = self.dimensions

                try:
                    response = client.post(
                        endpoint,
                        headers=self._headers(),
                        json=payload,
                    )
                except httpx.RequestError as exc:
                    raise EmbeddingError(
                        f"HTTP connection failed during embedding generation: {exc}"
                    ) from exc

                if response.status_code != 200:
                    raise EmbeddingError(
                        f"Embedding provider returned status {response.status_code}: "
                        f"{response.text}"
                    )

                data = response.json()
                items = data.get("data", [])
                if len(items) != len(batch):
                    raise EmbeddingError(
                        f"Embedding provider returned {len(items)} items for "
                        f"batch of {len(batch)}"
                    )

                # Sort by index if returned
                items_sorted = sorted(items, key=lambda x: x.get("index", 0))
                for item in items_sorted:
                    raw_vec: list[float] = item.get("embedding", [])
                    if len(raw_vec) != self.dimensions:
                        raise EmbeddingError(
                            f"Embedding dimension mismatch: expected "
                            f"{self.dimensions}, got {len(raw_vec)}"
                        )
                    all_embeddings.append(_l2_normalize(raw_vec))

        return all_embeddings

    def embed_query(self, text: str) -> list[float]:
        """Generate embedding for a single search query."""
        results = self.embed_texts([text])
        if not results:
            raise EmbeddingError("No embedding vector returned for query text.")
        return results[0]
