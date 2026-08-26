"""Tests for EmbeddingProvider protocol implementations."""

import math
from unittest.mock import MagicMock, patch

import httpx
import pytest

from platform_api.apps.processing.embedding import (
    EmbeddingError,
    EmbeddingProvider,
    get_embedding_provider,
)
from platform_api.apps.processing.embedding.fake_provider import FakeEmbeddingProvider
from platform_api.apps.processing.embedding.openai_provider import (
    OpenAICompatibleProvider,
)


def _vector_norm(v: list[float]) -> float:
    """Calculate Euclidean norm of a vector."""
    return math.sqrt(sum(x * x for x in v))


def test_fake_embedding_provider_contract() -> None:
    """
    FakeEmbeddingProvider satisfies the EmbeddingProvider Protocol and returns
    normalized vectors.
    """
    provider = FakeEmbeddingProvider(dimensions=1536)
    assert isinstance(provider, EmbeddingProvider)

    texts = ["First chunk text", "Second chunk text"]
    embeddings = provider.embed_texts(texts)

    assert len(embeddings) == 2
    assert len(embeddings[0]) == 1536
    assert len(embeddings[1]) == 1536

    # Verify L2 normalization
    assert math.isclose(_vector_norm(embeddings[0]), 1.0, rel_tol=1e-4)
    assert math.isclose(_vector_norm(embeddings[1]), 1.0, rel_tol=1e-4)

    # Verify determinism: identical text produces identical vector
    emb_repeat = provider.embed_texts(["First chunk text"])[0]
    assert embeddings[0] == emb_repeat

    # Verify query embedding matches
    query_vec = provider.embed_query("First chunk text")
    assert query_vec == embeddings[0]


def test_openai_compatible_provider_success() -> None:
    """
    OpenAICompatibleProvider parses batch response, applies L2 normalization,
    and handles batching.
    """
    provider = OpenAICompatibleProvider(
        base_url="https://mock.openai.com/v1",
        api_key="test-key",
        model_id="text-embedding-3-small",
        dimensions=4,
        max_batch_size=2,
    )

    mock_resp1 = {
        "data": [
            {"index": 0, "embedding": [1.0, 1.0, 1.0, 1.0]},
            {"index": 1, "embedding": [2.0, 0.0, 0.0, 0.0]},
        ]
    }
    mock_resp2 = {
        "data": [
            {"index": 0, "embedding": [0.0, 3.0, 4.0, 0.0]},
        ]
    }

    mock_client = MagicMock()
    mock_client.post.side_effect = [
        httpx.Response(
            200,
            json=mock_resp1,
            request=httpx.Request("POST", "https://mock.openai.com/v1/embeddings"),
        ),
        httpx.Response(
            200,
            json=mock_resp2,
            request=httpx.Request("POST", "https://mock.openai.com/v1/embeddings"),
        ),
    ]

    with patch("httpx.Client") as mock_client_cls:
        mock_client_cls.return_value.__enter__.return_value = mock_client
        results = provider.embed_texts(["text 1", "text 2", "text 3"])

    assert len(results) == 3
    assert len(results[0]) == 4
    # Vector [1,1,1,1] normalized is [0.5, 0.5, 0.5, 0.5]
    assert math.isclose(results[0][0], 0.5)
    # Vector [0, 3, 4, 0] normalized has norm 1.0
    assert math.isclose(_vector_norm(results[2]), 1.0)


def test_openai_compatible_provider_dimension_mismatch() -> None:
    """
    OpenAICompatibleProvider raises EmbeddingError if provider returns
    mismatched dimensions.
    """
    provider = OpenAICompatibleProvider(
        base_url="https://mock.openai.com/v1",
        dimensions=1536,
    )

    mock_resp = {
        "data": [
            {"index": 0, "embedding": [0.1, 0.2, 0.3]},  # 3 dims instead of 1536
        ]
    }

    mock_client = MagicMock()
    mock_client.post.return_value = httpx.Response(
        200,
        json=mock_resp,
        request=httpx.Request("POST", "https://mock.openai.com/v1/embeddings"),
    )

    with patch("httpx.Client") as mock_client_cls:
        mock_client_cls.return_value.__enter__.return_value = mock_client
        with pytest.raises(EmbeddingError, match="dimension mismatch"):
            provider.embed_texts(["sample text"])


def test_openai_compatible_provider_error_status() -> None:
    """OpenAICompatibleProvider raises EmbeddingError on non-200 responses."""
    provider = OpenAICompatibleProvider(
        base_url="https://mock.openai.com/v1",
        dimensions=1536,
    )

    mock_client = MagicMock()
    mock_client.post.return_value = httpx.Response(
        429,
        text="Rate limit exceeded",
        request=httpx.Request("POST", "https://mock.openai.com/v1/embeddings"),
    )

    with patch("httpx.Client") as mock_client_cls:
        mock_client_cls.return_value.__enter__.return_value = mock_client
        with pytest.raises(EmbeddingError, match="status 429"):
            provider.embed_texts(["sample text"])


def test_get_embedding_provider_factory(settings) -> None:
    """get_embedding_provider correctly resolves provider class from settings."""
    settings.EMBEDDING_PROVIDER_BACKEND = (
        "platform_api.apps.processing.embedding.fake_provider.FakeEmbeddingProvider"
    )
    provider = get_embedding_provider()
    assert isinstance(provider, FakeEmbeddingProvider)
