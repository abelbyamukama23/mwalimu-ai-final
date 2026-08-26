# ADR-007: Processing Identity, Idempotency, and Versioned Embeddings

## Status

Accepted

## Context

Document processing pipelines must support safe retries, deduplication, atomic version upgrades, and rolling rollbacks without corrupting or duplicating chunks or vector embeddings.

## Decision

We establish an immutable processing identity model, stage-level idempotency, and explicit versioning across pipeline components.

### 1. Processing Identity

A `ProcessingRun` is uniquely identified by the tuple:
`(resource, source_checksum, pipeline_version, extractor_version, chunker_version, embedding_model, embedding_version)`

Enforced via a partial unique index on `ProcessingRun` for rows where `status != 'failed'`. A failed run does not block subsequent attempts.

### 2. Versioned Chunk Embeddings

`ChunkEmbedding` is uniquely identified by:
`(chunk, embedding_model, embedding_version)`

A single `DocumentChunk` can possess multiple versioned embeddings across different model generations. Re-embedding does not destructively overwrite prior embeddings, making rollback immediate and cost-effective.

### 3. Atomic Activation and Run Retention

- Only one `ProcessingRun` per `Resource` has `is_active=True` (enforced by a partial unique index).
- When a new run succeeds, `is_active` is toggled atomically in a single database transaction: `new_run.is_active = True`, `previous_run.is_active = False`.
- Inactive runs and their associated chunks/embeddings are retained for audit and rollback purposes.
- Only the active run participates in vector retrieval.

### 4. Idempotency Guarantees

- **Stage 1 (Extract/Normalize/Chunk)**: Pure in-memory operations producing deterministic output.
- **Stage 2 (Embed)**: Batched writes using `get_or_create` semantics skipping chunks already embedded for that model and version.
- **Stage 3 (Index/Activate)**: Transactional chunk insertion and atomic `is_active` promotion.

## Consequences

### Positive

- Celery retries and duplicate task deliveries cannot produce duplicate chunks or embeddings.
- Non-destructive upgrades and zero-downtime rollback for embedding models.
- Clean separation between immutable processing artifacts and active searchable state.

### Negative

- Storing inactive historical runs and versioned embeddings increases database storage consumption, requiring future retention/pruning policies.

## Alternatives Considered

- **Destructive in-place re-chunking/embedding**: Rejected because it prevents zero-downtime rollbacks and complicates transaction boundaries during long-running embedding jobs.

## Related Decisions

- ADR-005: Chunking Strategy and Provenance Fields.
- ADR-006: pgvector Schema and Indexing.
- ADR-008: Celery Pipeline Topology.
