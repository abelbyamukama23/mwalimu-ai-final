# ADR-019: Durable AgentRun Persistence and Canonical Session Transcript Model

## Status
Proposed (Slice 7 Revised Design)

## Context
In Slice 6, the Agent Service (`agent_service/`) was established as an independent FastAPI service running in-memory cognitive reasoning loops (`AgentRun`), capability executions (`ToolRegistry`), and real-time SSE streaming.

In accordance with **ADR-001 (Service Boundaries)** and **ADR-012 (Agent Runtime Boundary)**:
1. **The Platform API is the sole System of Record.** Persistent domain state, audit history, multi-turn conversational sessions, user permissions, resource authorizations, and billing/token metrics must be owned and persisted by the Platform API in PostgreSQL.
2. **The Agent Service must NEVER access PostgreSQL or pgvector directly.** The Agent Service is an ephemeral, compute-oriented execution engine.
3. **Canonical Transcript Ownership**: Users interact in long-lived conversational threads (sessions). The Platform API must own the canonical transcript, while the Agent Service receives a runtime projection of conversation history and manages context-window token budgeting.
4. **Single-Process Execution Boundary**: Agent Service execution state is node-local and in-memory in this slice; horizontal multi-worker execution is NOT assumed.

## Decision

### 1. Platform API System-of-Record Domain Models (`platform_api/apps/agents/models.py`)
We will introduce three core models in the Platform API:

1. **`AgentSession`**:
   - Represents a long-lived conversational thread scoped to an authenticated user and an optional library/institution context.
   - Fields: `id` (UUID PK), `user` (FK to `users.User`), `institution` (FK to `institutions.Institution`), `primary_library` (FK to `libraries.Library`, null=True), `title` (str), `status` (`ACTIVE`, `ARCHIVED`), `created_at`, `updated_at`, `metadata` (JSON).

2. **`AgentRunRecord`**:
   - The durable system-of-record ledger of every dispatched agent execution.
   - Fields:
     - `id` (UUID PK, matches `agent_run_id`)
     - `session` (FK to `AgentSession`, related_name="runs")
     - `user` (FK to `users.User`)
     - `prompt` (TextField)
     - `status` (`CREATED`, `QUEUED`, `RUNNING`, `AWAITING_INPUT`, `COMPLETED`, `FAILED`, `CANCELLED`, `TIMED_OUT`)
     - `answer` (TextField, nullable)
     - `citations` (JSONField, list of 14-field citation objects)
     - `error_code` (CharField, nullable)
     - `error_message` (TextField, nullable)
     - `step_count` (PositiveIntegerField, default=0)
     - `prompt_tokens` (PositiveIntegerField, default=0)
     - `completion_tokens` (PositiveIntegerField, default=0)
     - `total_tokens` (PositiveIntegerField, default=0)
     - `timeout_seconds` (FloatField, default=60.0)
     - `max_steps` (PositiveIntegerField, default=10)
     - `created_at` (DateTimeField, auto_now_add=True)
     - `queued_at` (DateTimeField, auto_now_add=True)
     - `started_at` (DateTimeField, null=True, blank=True)
     - `finished_at` (DateTimeField, null=True, blank=True)

3. **`AgentSessionMessage`**:
   - Individual messages in the canonical conversational transcript.
   - Fields:
     - `id` (UUID PK)
     - `session` (FK to `AgentSession`, related_name="messages")
     - `run` (FK to `AgentRunRecord`, null=True, blank=True)
     - `role` (`user`, `assistant`, `system`)
     - `content` (TextField)
     - `citations` (JSONField, default=list, blank=True)
     - `sequence` (PositiveIntegerField)
     - `created_at` (DateTimeField, auto_now_add=True)
   - Constraints: `UniqueConstraint(fields=['session', 'sequence'], name='unique_session_sequence')`.

### 2. Canonical Transcript vs Runtime Context Projection
- **Platform API** retrieves past messages from `AgentSessionMessage` ordered by `sequence ASC`.
- **Platform API** serializes this history into a bounded list of `ModelMessage` objects (`USER`, `ASSISTANT`) passed to `POST /api/v1/runs`.
- **Agent Service** `WorkingContextBuffer` receives this history projection and enforces token budgeting during reasoning.
- There are **never two competing transcript authorities**.

### 3. Idempotent Completion Synchronization
- Endpoint: `POST /api/v1/internal/runs/{run_id}/completion/`
- Protected by `InternalServiceAuthentication`.
- Executes inside `transaction.atomic()` with `AgentRunRecord.objects.select_for_update()`.
- If `run_record` is already terminal, matching terminal updates are acknowledged idempotently; conflicting updates are safely ignored without corrupting state.
- Assistant transcript message creation is guarded by `unique_session_sequence` and transactional existence checks to prevent duplicate messages under retry.

## Consequences

### Positive
- Strict adherence to ADR-001: Platform API remains the sole system of record.
- Complete multi-turn session persistence across restarts and disconnects.
- Zero PostgreSQL access from the Agent Service runtime.
- High-fidelity 14-field citation provenance preserved across sessions.
- Fully idempotent completion synchronization handles retries cleanly.

### Explicit Architectural Invariants
- **S7-01**: Platform API is the durable system of record.
- **S7-02**: Agent Service is an execution engine, not a durable business-state owner.
- **S7-04**: Completion synchronization is idempotent.
- **S7-05**: Platform API owns the canonical session transcript.
