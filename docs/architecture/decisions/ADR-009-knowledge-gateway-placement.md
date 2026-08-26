# ADR-009: Knowledge Gateway Placement and Boundary

## Status

Accepted

## Context

The Mwalimu platform requires a retrieval mechanism to query vector embeddings and document chunks stored in PostgreSQL + pgvector (Slice 4). Consumers of this knowledge include the Agent Service (FastAPI running OpenAI Agents SDK), external AI tools via MCP, and future web frontends. 

We must establish:
1. Where the retrieval logic resides (Platform API vs. Agent Service vs. standalone microservice).
2. The hard boundaries regarding direct database access.
3. How external and internal consumers interface with the knowledge store.
4. Boundary preservation with respect to existing Slices 1–4.

## Decision

We place the **Knowledge Gateway** (or Knowledge Retrieval Gateway) strictly **inside the Platform API** (`platform_api.apps.knowledge`) as a cohesive Django application module.

### Core Architectural Invariants

1. **System of Record Ownership**: The Platform API owns all persistent state, access policies, and pgvector storage. Direct access to PostgreSQL/pgvector is restricted to the Platform API.
2. **Zero Direct DB Access for Consumers**: The Agent Service, external MCP clients, and frontends **must never access PostgreSQL or pgvector directly**. All retrieval must pass through the Knowledge Gateway.
3. **No Agent Logic in Gateway**: The Knowledge Gateway is strictly deterministic, stateless, and authoritative. It performs authorization resolution, query embedding, vector candidate retrieval, and provenance assembly. It contains **no agent loop, no prompt construction, and no LLM reasoning**.
4. **Internal HTTPS Integration**: The Agent Service communicates with the Knowledge Gateway via internal HTTPS application endpoints (`POST /api/v1/knowledge/search/`) using short-lived delegated execution credentials.
5. **MCP Wraps the Gateway**: Future MCP servers expose retrieval capabilities to AI clients by invoking the Knowledge Gateway API; MCP servers never bypass the Gateway.
6. **No Generic RAG Frameworks**: We explicitly reject third-party RAG frameworks (LangChain, LlamaIndex, Haystack). Retrieval is implemented using explicit, maintainable, pure-Python domain components.
7. **Strict Slice Boundary Preservation**:
   - Knowledge Gateway does NOT modify the `Resource` model (Slice 3).
   - Knowledge Gateway does NOT access object storage (Slice 3).
   - Knowledge Gateway does NOT manage document processing, text normalization, or chunking pipelines (Slice 4).
   - Knowledge Gateway reuses the `EmbeddingProvider` protocol and configured provider from Slice 4 (`platform_api.apps.processing.embedding.get_embedding_provider`) without moving or duplicating embedding generation code.
   - Knowledge Gateway strictly consumes the outputs of Slice 4 (`chunk_embedding`, `document_chunk`, `processing_run`).

## Consequences

### Positive

- Centralized authorization and security enforcement in the authoritative system of record.
- Clean decoupling between retrieval/provenance (Platform API) and reasoning/planning (Agent Service).
- pgvector connection pools and query plans remain centralized and isolated.
- Zero network hops between authorization policy evaluation and pgvector SQL execution.
- Existing Slice 1–4 architecture, models, and boundaries remain intact and pristine.

### Negative

- Retrieval queries from the Agent Service introduce an internal HTTP round trip.
- Requires maintenance of internal service-to-service authentication and delegation mechanisms.

## Alternatives Considered

- **Embedding retrieval directly in Agent Service**: Rejected per ADR-001 and AGENTS.md; the Agent Service must not connect to PostgreSQL or manage domain access policies.
- **Standalone Retrieval Microservice**: Rejected per AGENTS.md ("No microservices unless justified"); creates unnecessary operational complexity and duplicate database connections without scaling justification.
- **Generic RAG Frameworks (LangChain / LlamaIndex)**: Rejected per ADR-002; bespoke Clean Architecture components provide deterministic behavior, precise provenance, and zero dependency bloat.

## Related Decisions

- ADR-001: Service Boundaries.
- ADR-002: Dependency and Runtime Architecture.
- ADR-006: pgvector Schema and Indexing.
- ADR-010: Server-Authoritative Retrieval Authorization Model.
- ADR-011: Retrieval API Contract and Provenance Specification.
