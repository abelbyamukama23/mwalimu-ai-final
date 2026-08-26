# ADR-006: pgvector Schema and Indexing

## Status

Accepted

## Context

Mwalimu stores high-dimensional embeddings and conducts similarity searches within PostgreSQL using the `pgvector` extension. We must establish a multi-tenant vector schema that guarantees strict authorization boundaries and prevents unauthorized data leaks.

## Decision

We use PostgreSQL + `pgvector` via the official `pgvector` Python package (`VectorField`), rejecting separate vector databases (Pinecone, Qdrant, Weaviate) or per-tenant/per-library database schemas.

### Schema and Index Structure

1. **Vector Storage**: `ChunkEmbedding.vector` uses `VectorField(dimensions=1536)` (configured for the initial MVP model).
2. **HNSW Index**: Indexed with Hierarchical Navigable Small World (`HNSW`) using `vector_cosine_ops` for fast, recall-preserving approximate nearest neighbor (ANN) search.
3. **B-Tree Indexes**: B-Tree indexes on `DocumentChunk.library_id`, `DocumentChunk.resource_id`, and `DocumentChunk.processing_run_id` to accelerate scoped filtering and lifecycle operations.

### Mandatory Invariant: Authorization Before Vector Search

The vector database is **not** an authorization layer. Scoped similarity search must enforce authorization predicates in the query filter before vector similarity results are selected:

```sql
SELECT c.id, c.text, c.page_start, c.section,
       e.vector <=> %(query_vector) AS distance
FROM chunk_embedding e
JOIN document_chunk c ON c.id = e.chunk_id
JOIN processing_run pr ON pr.id = c.processing_run_id
WHERE c.library_id = ANY(%(authorized_library_ids))
  AND (%(authorized_resource_ids) IS NULL OR c.resource_id = ANY(%(authorized_resource_ids)))
  AND pr.is_active IS TRUE
  AND e.embedding_model = pr.embedding_model
  AND e.embedding_version = pr.embedding_version
  AND e.dimensions = pr.embedding_dimensions
ORDER BY e.vector <=> %(query_vector)
LIMIT %(top_k);
```

Under no circumstances may an unscoped vector search be executed with post-hoc authorization filtering.

## Consequences

### Positive

- Unified transactional consistency and ACID guarantees for relational metadata and vector embeddings.
- Elimination of distributed state synchronization across separate vector stores.
- Strict isolation preventing unauthorized vectors from ever entering candidate sets.

### Negative

- High vector query volume shares PostgreSQL connection pools with core transactional traffic, requiring careful connection and worker tuning.

## Alternatives Considered

- **Separate Vector Databases (Pinecone, Qdrant)**: Rejected per ADR-001/002 to avoid operational complexity and multi-system consistency hazards.
- **Post-search authorization filtering**: Rejected as a critical security vulnerability that risks candidate pool exhaustion and unauthorized metadata leaks.

## Related Decisions

- ADR-001: Service Boundaries.
- ADR-004: Embedding Provider Boundary.
- ADR-007: Processing Identity, Idempotency, and Versioned Embeddings.
