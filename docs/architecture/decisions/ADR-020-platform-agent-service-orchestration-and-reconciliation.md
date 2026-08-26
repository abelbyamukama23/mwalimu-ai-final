# ADR-020: Platform API ↔ Agent Service Orchestration, Delegation, and Crash Recovery

## Status
Proposed (Slice 7 Revised Design)

## Context
Integrating the Platform API (Django + DRF system of record) with the Agent Service (FastAPI reasoning runtime) requires strict protocol definitions for:
1. **Control Plane Boundary**: Frontend and student/teacher UIs communicate exclusively with Platform API, not internal Agent Service infrastructure.
2. **Four Disjoint Credential Domains**: User auth, Platform-to-Agent dispatch, Knowledge Gateway delegation, and Model Gateway provider keys must remain strictly segregated.
3. **Watchdog Reconciliation Semantics**: Distinguishing queue timeouts from execution timeouts.
4. **Cooperative Cancellation**: Handling cancellations across service boundaries safely and idempotently.
5. **Process-Local Execution Boundaries**: Explicitly recognizing that Agent Service execution is node-local in this slice.

## Decision

### 1. Platform API as the Client-Facing Control Plane
- The Mwalimu UI / client interacts **exclusively with Platform API**:
  $$\text{Client / UI} \longrightarrow \text{Platform API} \longrightarrow \text{Agent Service}$$
- Platform API owns user authentication, authorization, session management, durable run queries, cancellation requests, and transcript history.
- Agent Service is an internal backend compute engine, never directly exposed to public client traffic.

### 2. Four Disjoint Credential Domains
We establish four completely separate credential boundaries:

```
Domain A: End-User Authentication Credential
- Client -> Platform API
- Handled by DRF SimpleJWT (SIMPLE_JWT with SIGNING_KEY).
- Authenticates the user and establishes caller identity.

Domain B: Platform API -> Agent Service Dispatch Credential
- Platform API -> Agent Service (`POST /api/v1/runs`)
- Signed JWT (iss: "mwalimu-platform-api", sub: str(user_id), aud: "mwalimu-agent-service").
- Authenticates the dispatch to the internal Agent Service.

Domain C: DelegatedExecutionToken
- Agent Service -> Platform API Slice 5 Knowledge Gateway (`POST /api/v1/knowledge/search/`)
- Short-lived HMAC-SHA256 token minted exclusively by Platform API (`mint_delegated_token`), passed in `X-Delegated-Token` during dispatch, stored in `DelegatedCredentialVault`.
- Aud: "mwalimu-knowledge-gateway". Injected into Authorization: Bearer solely by KnowledgeSearchTool.
- MUST NOT be reused for completion synchronization.

Domain D: Internal Service Completion Credential
- Agent Service -> Platform API (`POST /api/v1/internal/runs/{run_id}/completion/`)
- Authenticated via dedicated internal HMAC service key / header `X-Internal-Service-Key`.
- Completely distinct from DelegatedExecutionToken.

Domain E: Model Provider Credentials
- Agent Service -> LLM Providers (DeepSeek, OpenAI, Gemini)
- Stored exclusively in Agent Service environment variables. Never accessible to Platform API or users.
```

### 3. Correct Watchdog Timeout Semantics
The watchdog reconciliation task distinguishes queue waiting time from reasoning execution time:

1. **QUEUED Timeout (`QUEUED_TIMEOUT_SECONDS = 60.0`)**:
   - If an `AgentRunRecord` is in `QUEUED` status and $\text{now}() > \text{queued\_at} + 60\text{s}$:
     - Mark `TIMED_OUT` (Reason: `QUEUED_TIMEOUT: Run was never dispatched/picked up`).
2. **RUNNING Execution Timeout (`run_record.timeout_seconds`)**:
   - Measured strictly from `started_at` (NOT `created_at` or `queued_at`).
   - If $\text{now}() > \text{started\_at} + \text{timeout\_seconds} + 30\text{s}$ (grace period):
     - Probe Agent Service: `GET /api/v1/runs/{id}`.
     - If Agent Service returns 404 or is unreachable: transition `run_record` to `TIMED_OUT` (Reason: `EXECUTION_TIMEOUT: Run exceeded execution budget and worker is unreachable`).

### 4. Cooperative Cancellation across the Service Boundary
When a client requests cancellation (`POST /api/v1/runs/{run_id}/cancel/`):
1. Platform API checks ownership (`run_record.user == request.user`).
2. Inside `transaction.atomic()`:
   - If `run_record.is_terminal`: return current status idempotently.
   - Transition `run_record.status = 'CANCELLED'`, `run_record.finished_at = timezone.now()`.
3. Platform API dispatches synchronous best-effort cancellation to Agent Service: `POST /api/v1/runs/{run_id}/cancel`.
   - If Agent Service is reachable: cancellation event token is signaled immediately.
   - If Agent Service is unreachable / fails: Platform API state is already marked `CANCELLED`. Subsequent completion callbacks from late execution will be safely ignored by the idempotent completion handler.

### 5. Explicit Process-Local Execution Boundary
- In Slice 7, Agent Service execution state (`InMemoryRunStore`, `asyncio.Task`, event queues) is **process-local**.
- Horizontal clustering / multi-worker distributed state is **NOT assumed or supported** in this slice.
- If an Agent Service node restarts, active in-memory runs terminate; the Platform API watchdog cleanly transitions orphaned records to terminal states.
- Distributed execution/clustering is deferred to a future dedicated architecture decision.

## Consequences

### Architectural Invariants Established
- **S7-03**: User credentials, Agent Service credentials, DelegatedExecutionTokens, and model-provider credentials are separate security domains.
- **S7-06**: Agent Service horizontal scaling is NOT assumed while execution state remains process-local.
- **S7-07**: Existing infrastructure must be reused before introducing new infrastructure.
- **S7-08**: Frontend clients interact with Platform API rather than internal Agent Service infrastructure.
- **S7-09**: Cancellation must be explicitly defined across the Platform API $\rightarrow$ Agent Service boundary.
- **S7-10**: Watchdog timeout semantics distinguish queue time from execution time.
