# ADR-008: Celery Pipeline Topology

## Status

Accepted

## Context

Processing uploaded documents into searchable embeddings requires asynchronous execution to avoid blocking HTTP request/response lifecycles. We must choose an asynchronous job topology that minimizes distributed failure modes and handles retries reliably.

## Decision

We use Celery with Redis as the message broker, implementing a **single orchestrating task** (`process_resource_run(run_id)`) rather than a multi-task Celery chain or canvas.

### Pipeline Topology and Lifecycle

1. **Single Task Boundary**: `process_resource_run` coordinates the sequential stages in-process:
   ```
   verify integrity → extract → normalize → chunk → embed → index/activate
   ```
2. **Intermediate Data Handling**: Intermediate text and embeddings are maintained in-process memory or committed to PostgreSQL, avoiding serialization of multi-megabyte payloads across Redis broker queues.
3. **Queue Architecture**: Dedicated `ingestion` queue with `worker_prefetch_multiplier = 1` and `acks_late = True` for fair scheduling of long-running parsing tasks.
4. **Retry and Failure Semantics**:
   - `autoretry_for` transient exceptions (network dropouts, rate limits, deadlock errors) with exponential backoff and jitter (`max_retries = 5`).
   - Permanent errors (e.g. corrupt files, `EMPTY_EXTRACTION`) fail immediately without retry, marking the run `FAILED` with specific `error_code` and cleaning up any partial chunks.
5. **Concurrency Control vs. Correctness**:
   - Opportunistic Redis distributed lock per `resource_id` (`SET NX EX 900`) prevents redundant concurrent worker contention.
   - **Correctness Boundary**: Redis locking is strictly a concurrency optimization. Core correctness is guaranteed by PostgreSQL database constraints and stage-level idempotency. If Redis loses lock state, database constraints prevent data corruption.

## Consequences

### Positive

- Simple operational footprint with no distributed canvas failure modes.
- No broker bloat from large intermediate extracted texts.
- Deterministic retry handling with comprehensive stage error recording.

### Negative

- Monolithic task execution means worker processes hold tasks during slow external embedding API calls (mitigated via batching and rate-limit backoff).

## Alternatives Considered

- **Celery Canvas / Chains (extract | normalize | chunk | embed | index)**: Rejected because passing intermediate data through Redis adds serialization overhead, and stage failure recovery becomes fragile across tasks.
- **Distributed Workflow Engines (Temporal / Airflow)**: Rejected per ADR-002 as excessive operational complexity for Mwalimu's architecture.

## Related Decisions

- ADR-001: Service Boundaries.
- ADR-002: Dependency and Runtime Architecture.
- ADR-007: Processing Identity, Idempotency, and Versioned Embeddings.
