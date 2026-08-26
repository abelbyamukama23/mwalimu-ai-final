# ADR-004: Embedding Provider Boundary

## Status

Accepted

## Context

Mwalimu generates dense vector representations of document chunks for semantic indexing and retrieval. We require an architectural boundary separating the core knowledge domain from specific embedding vendors, while supporting self-hosted (vLLM, Ollama) and cloud-hosted embedding APIs.

## Decision

We establish an explicit `EmbeddingProvider` Python `Protocol` as an architectural boundary. Domain code (`processing`, `indexing`, `tasks`, models) interacts exclusively with this protocol:

```python
class EmbeddingProvider(Protocol):
    model_id: str
    embedding_version: str
    dimensions: int
    max_batch_size: int

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
```

### Key Requirements

1. **Decoupled Client**: The domain layer never imports the `openai` SDK or vendor-specific libraries. An HTTP adapter built on `httpx` implements the protocol against standard OpenAI-compatible `/v1/embeddings` endpoints.
2. **Explicit Metadata**: The provider explicitly exposes `model_id`, `embedding_version`, and `dimensions`.
3. **Deployment Default**: The MVP deployment uses `text-embedding-3-small` with 1536 dimensions and cosine distance. However, 1536 dimensions is a deployment configuration, not an immutable Mwalimu-wide conceptual constant.
4. **Vector Normalization**: Vectors are L2-normalized before persistence to ensure cosine distance equivalence with inner product operations.
5. **Agent Independence**: Agent Service model configuration and Platform API embedding model configuration are decoupled and managed independently.

## Consequences

### Positive

- Zero vendor SDK lock-in in domain models and services.
- Seamless swapping of embedding backends (e.g. OpenAI, Azure OpenAI, Ollama, vLLM, HuggingFace TEI) by modifying environment variables.
- Deterministic testing enabled through in-memory `FakeEmbeddingProvider`.

### Negative

- Changes to embedding dimensions necessitate deliberate database schema migrations due to PostgreSQL `vector(N)` fixed-width storage.

## Alternatives Considered

- **Official OpenAI SDK**: Rejected because it couples domain logic to a specific vendor library and adds unnecessary dependencies for a single HTTP endpoint.
- **LangChain / LlamaIndex embedding abstractions**: Rejected per ADR-002.
- **Database-internal embedding generation**: Rejected to avoid tight coupling between database extensions and external network calls.

## Related Decisions

- ADR-001: Service Boundaries.
- ADR-002: Dependency and Runtime Architecture.
- ADR-006: pgvector Schema and Indexing.
