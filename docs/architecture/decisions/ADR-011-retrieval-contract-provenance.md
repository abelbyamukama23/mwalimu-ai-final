# ADR-011: Retrieval API Contract and Provenance Specification

## Status

Accepted

## Context

Downstream consumers (the Agent Service and future MCP tools) require relevant document chunks to ground LLM reasoning and cite factual sources accurately. 

We must define:
1. The stable request and response schema for the Knowledge Gateway.
2. The exact evidence fields returned with every chunk for citation grounding.
3. Server-side query embedding generation and limit clamping.
4. The single-query SQL retrieval architecture.
5. Pragmatic Clean Architecture boundaries avoiding over-engineering.

## Decision

We define a stable, versioned API endpoint (`POST /api/v1/knowledge/search/`), an exhaustive **14-field Provenance Contract**, and a pragmatic 4-layer Clean Architecture structure.

### 1. Request Contract Boundary

The Gateway strictly differentiates caller-provided inputs from server-derived execution parameters:

- **Caller-Provided**: `query` (text, 1–10,000 chars), `library_ids` (optional filter list), `resource_ids` (optional filter list), `top_k` (optional integer, clamped to $[1, 50]$, default `10`), `similarity_threshold` (optional float, $[0.0, 1.0]$), `include_text` (optional boolean, default `true`).
- **Server-Derived**: `user_id` (from validated user JWT or delegated execution credential), `authorized_library_ids` and `authorized_resource_ids` (via immutable `EffectiveRetrievalScope`), `query_vector` (via `EmbeddingProvider.embed_query`), `embedding_model`, `embedding_version`, `dimensions`, `effective_top_k`.

Callers **never** supply query vectors or model metadata.

### 2. The 14-Field Evidence Contract

Every retrieved item returns complete evidence for grounding and verification:

1. `chunk_id`: Unique chunk UUID (`DocumentChunk.id`).
2. `score`: Cosine similarity ($1.0 - \text{distance}$), bounded in $[0.0, 1.0]$.
3. `text`: Exact chunk text content.
4. `resource_id`: Source resource UUID (`Resource.id`).
5. `resource_name`: Source human-readable name (`Resource.name`).
6. `library_id`: Owning library UUID (`Library.id`).
7. `library_name`: Owning library name (`Library.name`).
8. `page_start`: 1-indexed starting page (integer or `null`).
9. `page_end`: 1-indexed ending page (integer or `null`).
10. `section`: Enclosing heading path (string or `null`).
11. `sequence`: Sequential chunk index within the processing run.
12. `char_start`: Starting character offset in normalized text.
13. `char_end`: Ending character offset in normalized text.
14. `content_sha256`: SHA-256 digest of the chunk text for tamper verification.

### 3. Single-Query SQL Retrieval

Retrieval is executed in a single atomic SQL query joining `chunk_embedding`, `document_chunk`, `processing_run`, `resources_resource`, and `libraries_library`. It applies authorization predicates in the `WHERE` clause prior to vector distance ordering (`<=>`), enforcing:
- `c.library_id = ANY(%(authorized_library_ids)s)`
- `pr.is_active IS TRUE` and `pr.status = 'ready'`
- Embedding model, version, and dimension consistency matching the active run.

### 4. Pragmatic Architectural Boundaries

We adopt a streamlined, non-ceremonial 4-layer design:
- **Presentation**: `views.py` (DRF view), `serializers.py` (DRF validation & response DTOs), `authentication.py` (Delegated token validator).
- **Application**: `use_cases.py` (`SearchKnowledgeUseCase` orchestrating retrieval workflow).
- **Domain**: `policies.py` (`KnowledgeAuthorizationPolicy`, `EffectiveRetrievalScope`), `contracts.py` (`RetrieverProtocol`, `QueryEmbedderProtocol`).
- **Infrastructure**: `pgvector_retriever.py` (`PgVectorRetriever`), `embedding_adapter.py` (`EmbeddingProviderAdapter` wrapping Slice 4's `EmbeddingProvider`), `audit_logger.py`.

*Exclusions*: Redundant domain entities, custom string wrapper value objects, and extra repository interfaces are rejected as unnecessary ceremonial complexity.

## Consequences

### Positive

- Complete, unambiguous evidence returned for citation and auditability.
- Single database round-trip minimizes retrieval latency ($\le 30\text{ms}$ on indexed data).
- Strict server clamping prevents denial-of-service or memory bloat.
- High testability with zero ceremonial architectural overhead.

### Negative

- Rich provenance payloads slightly increase JSON response payload size compared to raw text.

## Alternatives Considered

- **Two-Step Retrieval (IDs then lookup)**: Rejected; introduces extra database round-trips and query coordination overhead.
- **Returning Bare Chunks without Provenance**: Rejected; breaks the agent grounding invariant and makes hallucination detection impossible.
- **Complex Domain Layer (DDD aggregates/factories)**: Rejected; retrieval is an application use case querying read models; full domain aggregates add complexity without value.

## Related Decisions

- ADR-005: Chunking Strategy and Provenance Fields.
- ADR-006: pgvector Schema and Indexing.
- ADR-009: Knowledge Gateway Placement and Boundary.
- ADR-010: Server-Authoritative Retrieval Authorization & Delegation Model.
