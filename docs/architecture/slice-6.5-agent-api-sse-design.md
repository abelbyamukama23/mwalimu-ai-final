# Slice 6.5 Design: Agent Service HTTP API & Server-Sent Events (SSE) (Revised)

## 1. Overview & Objectives

Slice 6.5 introduces the presentation layer for the Mwalimu Agent Service (`agent_service/`), exposing the reasoning runtime through a secure, asynchronous RESTful HTTP API and real-time Server-Sent Events (SSE) streaming interface.

### Architectural Invariants:
1. **Reuse Existing Runtime**: Integrates `AgentRun`, `ExecutionContext`, `ReasoningLoop`, `ModelProviderProtocol`, `ToolRegistry`, and `DelegatedCredentialVault` without redesign or duplication.
2. **Cryptographic Authentication**: User identity is derived exclusively from cryptographically verified credentials (`AuthenticatedPrincipal`). `X-User-ID` or request-body identity injection is strictly prohibited.
3. **Internal Credential Isolation**: The `DelegatedExecutionToken` is an internal capability credential minted/injected exclusively by the trusted Platform/Agent execution boundary. It is **never** accepted in public client requests (`CreateRunRequest`) and never exposed in responses, events, or logs.
4. **Non-Escalating Capabilities**: Tool allowlists are server-authorized; client requests can only narrow the effective capability set ($\text{EffectiveAllowlist} = \text{ServerAuthorized} \cap \text{ClientRequested}$), never widen or grant new permissions.
5. **Authoritative State Machine**: `AgentRun` remains the sole source of truth for execution state. SSE events are a real-time observation projection, not a secondary state machine.
6. **Explicit Ephemeral Scheduling**: Execution scheduling is in-process (`asyncio.create_task` and `InMemoryRunStore`). Process restart, multi-worker, and crash durability limitations are explicitly documented.

---

## 2. System Architecture & Component Interactions

```mermaid
sequenceDiagram
    autonumber
    actor Client as Client / Platform API
    participant API as FastAPI Presentation Layer
    participant Auth as JWT Auth Dependency
    participant Store as InMemoryRunStore
    participant Vault as DelegatedCredentialVault
    participant UseCase as RunAgentUseCase
    participant Loop as ReasoningLoop
    participant Model as Model Gateway
    participant Tools as ToolRegistry (Slice 5 / Native)

    Client->>API: POST /api/v1/runs {prompt, session_id, ...} [Authorization: Bearer JWT]
    API->>Auth: Cryptographically Verify JWT
    Auth-->>API: AuthenticatedPrincipal(user_id=UUID)
    API->>API: Compute EffectiveToolAllowlist (ServerAuthorized ∩ ClientRequested)
    API->>Store: Create AgentRun (CREATED -> QUEUED)
    API->>Store: Register asyncio.Task & Cancellation Event
    API-->>Client: 202 Accepted {run_id, session_id, status: "queued"}

    Note over Client,API: Optional SSE Connection for Real-Time Streaming
    Client->>API: GET /api/v1/runs/{run_id}/events [Authorization: Bearer JWT]
    API->>Auth: Verify JWT & Check Run Ownership (user_id == run.user_id)
    API->>Store: Subscribe to Event Queue & Replay Past Events

    Note over UseCase,Loop: Asynchronous Background Execution (In-Process Task)
    Store->>UseCase: Execute Run in Background Task
    UseCase->>Loop: execute_run(run, context, prompt)
    Loop->>Store: Emit SSE Event: run.started
    
    loop Reasoning Cycle
        Loop->>Store: Emit SSE Event: step.started
        Loop->>Model: stream_generate(messages, tools)
        Model-->>Loop: Stream ModelStreamChunk
        Loop->>Store: Emit SSE Event: model.delta (tokens)
        
        opt Model Requests Tool
            Loop->>Store: Emit SSE Event: tool.started
            Loop->>Tools: execute(request, context)
            Note over Tools,Vault: Scoped Credential Injected inside Tool Adapter
            Tools-->>Loop: ToolResult + Evidence Citations
            Loop->>Store: Emit SSE Event: tool.completed
            Loop->>Store: Emit SSE Event: citation.added (14 fields)
        end
    end

    Loop->>Store: Transition to COMPLETED (or FAILED/TIMED_OUT)
    Loop->>Vault: Purge Delegated Token (if present)
    Loop->>Store: Emit SSE Event: run.completed
    API-->>Client: Stream SSE Events & Close Connection
```

---

## 3. Public HTTP API Contract

### 3.1 `POST /api/v1/runs` (Create & Dispatch Run)
- **Status**: `202 Accepted`
- **Headers**:
  - `Authorization: Bearer <user_jwt_token>` (Required)
  - `Content-Type: application/json`

#### Request Schema (`CreateRunRequest`)
```json
{
  "prompt": "Explain cellular respiration and calculate 25 * 4",
  "session_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "max_steps": 10,
  "timeout_seconds": 60.0,
  "token_budget": 4000,
  "locale": "en",
  "tool_allowlist": ["knowledge_search", "calculator"]
}
```

*Field Rules & Non-Escalation*:
- `prompt` (`str`, required): 1 to 10,000 characters.
- `session_id` (`UUID`, optional): Generated automatically if omitted.
- `max_steps` (`int`, optional, default `10`, range `1` to `50`).
- `timeout_seconds` (`float`, optional, default `60.0`, range `1.0` to `300.0`).
- `token_budget` (`int`, optional, default `4000`, range `100` to `32000`).
- `locale` (`str`, optional, default `"en"`).
- `tool_allowlist` (`list[str] | null`, optional): Narrowing tool allowlist. The effective allowlist is calculated as $\text{ServerTools} \cap \text{tool\_allowlist}$. Unauthorized tool requests are discarded.
- **NO `delegated_token`**: Delegated execution tokens are NEVER client-supplied.
- **NO `user_id`**: User identity is derived strictly from verified authentication.

#### Response Schema (`RunResponse`)
```json
{
  "run_id": "4fa85f64-5717-4562-b3fc-2c963f66afa8",
  "session_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "status": "queued",
  "prompt": "Explain cellular respiration and calculate 25 * 4",
  "answer": null,
  "citations": [],
  "error_code": null,
  "error_message": null,
  "step_count": 0,
  "total_prompt_tokens": 0,
  "total_completion_tokens": 0,
  "total_tokens": 0,
  "created_at": "2026-08-23T14:30:00Z",
  "started_at": null,
  "finished_at": null,
  "elapsed_seconds": 0.0
}
```

---

### 3.2 `GET /api/v1/runs/{run_id}` (Get Run Snapshot)
- **Status**: `200 OK` (or `404 Not Found`, `401 Unauthorized`)
- **Headers**:
  - `Authorization: Bearer <user_jwt_token>`

#### Completed Response Example:
```json
{
  "run_id": "4fa85f64-5717-4562-b3fc-2c963f66afa8",
  "session_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "status": "completed",
  "prompt": "Explain cellular respiration and calculate 25 * 4",
  "answer": "Cellular respiration produces ATP. 25 * 4 = 100.",
  "citations": [
    {
      "chunk_id": "e0b83b12-9856-49f3-8b7a-6b45a6c38f12",
      "score": 0.8842,
      "resource_id": "4fa85f64-5717-4562-b3fc-2c963f66afa7",
      "resource_name": "Biology101.pdf",
      "library_id": "3fa85f64-5717-4562-b3fc-2c963f66afa8",
      "library_name": "Biology Reference Library",
      "page_start": 42,
      "page_end": 43,
      "section": "Chapter 3",
      "sequence": 14,
      "char_start": 28400,
      "char_end": 30350,
      "content_sha256": "8f4e2b02..."
    }
  ],
  "error_code": null,
  "error_message": null,
  "step_count": 2,
  "total_prompt_tokens": 120,
  "total_completion_tokens": 45,
  "total_tokens": 165,
  "created_at": "2026-08-23T14:30:00Z",
  "started_at": "2026-08-23T14:30:01Z",
  "finished_at": "2026-08-23T14:30:04Z",
  "elapsed_seconds": 3.0
}
```

---

### 3.3 `POST /api/v1/runs/{run_id}/cancel` (Cancel Active Run)
- **Status**: `200 OK`
- **Headers**:
  - `Authorization: Bearer <user_jwt_token>`

#### Response Schema (`CancelRunResponse`)
```json
{
  "run_id": "4fa85f64-5717-4562-b3fc-2c963f66afa8",
  "status": "cancelled",
  "message": "Run execution cancelled successfully."
}
```

---

### 3.4 `GET /api/v1/runs/{run_id}/events` (Server-Sent Events Stream)
- **Status**: `200 OK`
- **Headers**:
  - `Authorization: Bearer <user_jwt_token>`
  - `Content-Type: text/event-stream`
  - `Cache-Control: no-cache`
  - `Connection: keep-alive`
  - `Last-Event-ID: <int>` (optional, for stream resumption)

---

## 4. Server-Sent Events (SSE) Protocol & Taxonomy

Events are observational projections of runtime execution:
```
id: 1
event: run.started
data: {"run_id": "4fa85f64...", "status": "running", "timestamp": "2026-08-23T14:30:01Z"}

id: 2
event: step.started
data: {"run_id": "4fa85f64...", "step": 1}

id: 3
event: model.delta
data: {"run_id": "4fa85f64...", "step": 1, "delta_content": "Photosynthesis "}

id: 4
event: tool.started
data: {"run_id": "4fa85f64...", "step": 1, "tool_name": "calculator", "call_id": "c1"}

id: 5
event: tool.completed
data: {"run_id": "4fa85f64...", "step": 1, "tool_name": "calculator", "call_id": "c1", "success": true}

id: 6
event: citation.added
data: {"run_id": "4fa85f64...", "citation": {"resource_name": "Bio.pdf", "page_start": 42, "score": 0.88}}

id: 7
event: run.completed
data: {"run_id": "4fa85f64...", "status": "completed", "answer": "...", "total_tokens": 165}

```

### Event Lifecycle Table:
| Event Name | Phase | Payload Contents | Closes Stream? |
|------------|-------|------------------|----------------|
| `run.created` | Initialization | `run_id`, `session_id`, `status` | No |
| `run.started` | Execution start | `run_id`, `started_at` | No |
| `step.started` | Step iteration | `run_id`, `step` | No |
| `model.delta` | Streaming token | `run_id`, `step`, `delta_content` | No |
| `tool.started` | Capability dispatch | `run_id`, `step`, `tool_name`, `call_id` | No |
| `tool.completed` | Capability outcome | `run_id`, `step`, `tool_name`, `call_id`, `success` | No |
| `citation.added` | Provenance grounding | `run_id`, `citation` (14 fields) | No |
| `run.completed` | Final success | `run_id`, `status`, `answer`, `citations`, `total_tokens` | **Yes** |
| `run.failed` | Error failure | `run_id`, `status`, `error_code`, `error_message` | **Yes** |
| `run.cancelled` | Cancellation | `run_id`, `status` | **Yes** |
| `run.timed_out` | Budget expiry | `run_id`, `status`, `error_message` | **Yes** |

---

## 5. Event Buffering & Reconnection Mechanics

1. **Per-Run Circular Event Buffer**: `InMemoryRunStore` stores all emitted events sequentially (`list[SSEEvent]`).
2. **Late Subscription**: If a client connects after execution has begun or completed, the endpoint replays all buffered events in order before streaming live events or closing.
3. **Resumption via `Last-Event-ID`**: If a client disconnects and reconnects with `Last-Event-ID: 15`, only events with `id > 15` are replayed.
4. **Terminal Runs**: If a run is already terminal (`COMPLETED`, `FAILED`, `CANCELLED`, `TIMED_OUT`), all buffered events are streamed immediately and the HTTP connection is closed cleanly.

---

## 6. Execution Scheduling & Operational Limitations

### Single-Process Ephemeral Architecture:
- Execution is scheduled in-process using `asyncio.create_task()` managed by `InMemoryRunStore`.
- Zero external broker dependencies (no Redis, Celery, Kafka, RabbitMQ).

### Explicit Operational Limitations:
1. **Process Restart**: Process restart terminates in-flight runs and purges in-memory event buffers.
2. **Process-Local Buffers**: SSE connections must reach the process hosting the run.
3. **Single Worker Process**: Multi-worker deployments without shared state are unsupported in Slice 6.5.
4. **No Crash Durability**: Durable state storage and multi-node event distribution are deferred to future architecture phases.

---

## 7. Authentication & Security Model

```
Client / Caller
      │  Authorization: Bearer <JWT>
      ▼
FastAPI Security Dependency (`get_authenticated_principal`)
      │  Cryptographically decodes & verifies signature, issuer, exp, sub
      ▼
AuthenticatedPrincipal(user_id=UUID, is_authenticated=True)
      │  Guarantees non-spoofable user identity
      ▼
ExecutionContext(user_id=principal.user_id, run_id=UUID, ...)
      │  Frozen value object; zero raw credentials
      ▼
DelegatedCredentialVault (Keyed by agent_run_id)
      │  Internal platform execution boundary credential
      ▼
KnowledgeSearchTool (Slice 5 Knowledge Gateway)
```

- **Tenancy & Ownership Check**: Every endpoint checks `run.context.user_id == principal.user_id`. Access attempts to another user's run return `404 Not Found`.
- **Capability Protection**: Client-supplied allowlists cannot widen capabilities beyond `tool_registry.list_definitions()`.

---

## 8. Deterministic HTTP Error Mapping

| Condition | HTTP Code | Response Code | Description |
|-----------|-----------|---------------|-------------|
| Malformed JSON / schema error | `422 Unprocessable Entity` | `VALIDATION_ERROR` | Request body failed Pydantic validation |
| Missing / invalid authentication | `401 Unauthorized` | `AUTHENTICATION_REQUIRED` | Missing or invalid Bearer JWT |
| Inaccessible / foreign run | `404 Not Found` | `RUN_NOT_FOUND` | Run does not exist or belongs to another user |
| Invalid state / duplicate cancel | `200 OK` (idempotent) / `409 Conflict` | `INVALID_STATE` | Operation on terminal run |
| Internal server error | `500 Internal Server Error` | `INTERNAL_ERROR` | Unexpected unhandled exception |

---

## 9. Reuse-Before-Build Audit

| Requirement | Existing Mechanism | Reused? | Decision & Rationale |
|-------------|--------------------|---------|----------------------|
| Web Framework | `FastAPI` (installed v0.115) | ✅ Yes | Async route handling and dependency injection |
| Schema Validation | `Pydantic v2` (installed v2.13) | ✅ Yes | Typed request/response models |
| Authentication | `PyJWT` (installed) / HMAC-SHA256 | ✅ Yes | Cryptographically verified Bearer token validation |
| State Machine | `AgentRun` (domain/run.py) | ✅ Yes | Single source of truth for lifecycle state |
| Runtime Boundaries | `ExecutionContext` (domain/context.py) | ✅ Yes | Immutable correlation and execution boundaries |
| Orchestration | `ReasoningLoop` (application/) | ✅ Yes | Background task execution engine |
| Streaming Inference | `ModelProviderProtocol.stream_generate` | ✅ Yes | Normalized token deltas projected to SSE |
| Capability Pipeline | `ToolRegistry` (infrastructure/) | ✅ Yes | 5-stage capability pipeline with allowlist narrowing |
| Credential Storage | `DelegatedCredentialVault` | ✅ Yes | Scoped vault for Slice 5 Knowledge Gateway access |
| Task Scheduling | `asyncio.create_task` | ✅ Yes | In-process asynchronous task registry |
| Distributed Brokers | Redis / Celery / Kafka / RabbitMQ | ❌ No | Rejected per YAGNI |
| Streaming Protocol | WebSockets | ❌ No | Rejected; SSE is simpler, unidirectional, and standard |
| Logging | Python `logging` stdlib | ✅ Yes | Structured audit logging without credentials |

---

## 10. Testing Plan for Slice 6.5

### 10.1 API Endpoint Tests (`tests/test_api_endpoints.py`)
- `test_create_run_success`: `POST /api/v1/runs` with valid JWT returns `202 Accepted` and dispatches background run.
- `test_create_run_unauthenticated`: `POST /api/v1/runs` without JWT returns `401 Unauthorized`.
- `test_create_run_tool_allowlist_narrowing`: Requesting `["calculator", "malicious_tool"]` narrows to `["calculator"]` only.
- `test_get_run_status_success`: `GET /api/v1/runs/{id}` returns correct status, answer, and 14-field citations.
- `test_get_run_status_isolation`: User B cannot access User A's run (`404 Not Found`).
- `test_cancel_run_success`: `POST /api/v1/runs/{id}/cancel` triggers cancellation token and transitions run to `CANCELLED`.
- `test_cancel_terminal_run_idempotency`: Cancelling an already completed run is safe and idempotent.

### 10.2 Server-Sent Events Tests (`tests/test_sse_streaming.py`)
- `test_sse_stream_full_lifecycle`: Stream yields `run.started` $\rightarrow$ `step.started` $\rightarrow$ `model.delta` $\rightarrow$ `tool.started` $\rightarrow$ `tool.completed` $\rightarrow$ `run.completed`.
- `test_sse_late_subscriber_replay`: Connecting after completion replays all buffered events and closes cleanly.
- `test_sse_last_event_id_resumption`: Reconnects with `Last-Event-ID` and receives only subsequent events.
- `test_sse_user_isolation`: User B cannot subscribe to User A's run events (`404 Not Found`).
- `test_sse_no_credential_leakage`: Verifies delegated tokens and internal headers never appear in SSE event payloads.

### 10.3 End-to-End Presentation Integration (`tests/test_presentation_integration.py`)
- Complete path:
  `HTTP Request` $\rightarrow$ `FastAPI` $\rightarrow$ `ReasoningLoop` $\rightarrow$ `FakeModelProvider` $\rightarrow$ `ToolRegistry` $\rightarrow$ `SSE Stream` $\rightarrow$ Final Answer + Citations.
