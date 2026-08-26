# ADR-018: Agent Service HTTP API and Server-Sent Events (SSE) Architecture

## Status
Proposed (Slice 6.5 Revised Design)

## Context
The Agent Service (`agent_service/`) contains the core cognitive execution runtime, state machine (`AgentRun`), working memory (`WorkingContextBuffer`), Model Gateway (`ModelProviderProtocol`), and capability execution pipeline (`ToolRegistry`).

To expose this runtime to clients (Platform API orchestration and authorized users), we require a high-performance, asynchronous HTTP interface with real-time streaming capabilities.

Key architectural and security requirements:
1. **Reuse-Before-Build**: Leverage existing FastAPI, Pydantic, and asyncio infrastructure without introducing unneeded message brokers (Kafka, RabbitMQ, Celery, Dramatiq) or WebSockets.
2. **Cryptographic Identity Verification**: Client user identity must NEVER be trusted from request bodies or unauthenticated headers (such as `X-User-ID`). Identity must be derived strictly from a cryptographically verified credential (`AuthenticatedPrincipal`).
3. **Internal Capability Credential Isolation**: The `DelegatedExecutionToken` is an internal capability credential minted/injected exclusively by the trusted Platform/Agent execution boundary. It is NEVER client-supplied in `CreateRunRequest` and never exposed in responses, events, or logs.
4. **Non-Escalating Tool Capabilities**: Tool capabilities are server-authorized. Client-supplied tool allowlists may only narrow the effective capability set ($\text{EffectiveAllowlist} = \text{ServerAuthorized} \cap \text{ClientRequested}$), never widen or grant new permissions.
5. **Deterministic Lifecycle & SSE Projection**: `AgentRun` remains the sole source of truth for lifecycle state. Server-Sent Events (SSE) act strictly as an observational projection/transport of runtime events, not a secondary state machine.
6. **Single-Process Ephemeral Scheduling**: In Slice 6.5, execution scheduling is intentionally single-process and in-memory (`asyncio.create_task` and `InMemoryRunStore`).

## Decision

### 1. Distinct Authentication Boundaries
We establish two completely separate authentication boundaries:

```
Boundary 1: Client -> Agent Service
- Authenticated via cryptographically verified Bearer token (JWT).
- Validated at the FastAPI security dependency boundary.
- Resolves to `AuthenticatedPrincipal(user_id=UUID, ...)`
- Request payloads cannot supply or override `user_id`.

Boundary 2: Agent Service -> Platform API (Slice 5 Knowledge Gateway)
- Authenticated via short-lived HMAC-SHA256 `DelegatedExecutionToken` (15-min TTL).
- Stored exclusively in `DelegatedCredentialVault` keyed by `agent_run_id`.
- Injected solely into `KnowledgeSearchTool` -> `Authorization: Bearer <delegated_token>`.
- Never accepted from public client request payloads (`CreateRunRequest`).
- Never exposed to LLM prompts, model messages, SSE events, or API responses.
```

### 2. Presentation Layer Boundary
The HTTP and SSE boundary resides in `agent_service/src/agent_service/presentation/`.

The dependency direction remains strictly downward:
```
Presentation Layer (FastAPI routes, SSE broadcaster, Pydantic schemas)
       │
       ▼
Application Layer (RunAgentUseCase, CancelRunUseCase, GetRunStatusUseCase, ReasoningLoop)
       │
       ▼
Domain Layer (AgentRun, ExecutionContext, Protocols, WorkingContextBuffer)
       ▲
       │
Infrastructure Layer (ModelGateway, ToolRegistry, DelegatedCredentialVault, InMemoryRunStore)
```

Presentation components MUST NOT:
- Directly access PostgreSQL or pgvector.
- Import provider vendor SDKs (`openai`, `google.genai`).
- Access raw delegated credentials.
- Execute tools directly (all invocations must route through `ToolRegistry`).
- Modify `ExecutionContext` fields.

### 3. HTTP Endpoints Contract
- `POST /api/v1/runs`: Create and dispatch a new agent execution run. Returns `202 Accepted` with run metadata.
- `GET /api/v1/runs/{run_id}`: Retrieve snapshot status, metrics, final answer, and citations.
- `POST /api/v1/runs/{run_id}/cancel`: Signal cooperative cancellation for an active run.
- `GET /api/v1/runs/{run_id}/events`: Stream real-time execution events via SSE (`text/event-stream`).

### 4. Non-Escalating Tool Allowlist Semantics
The client request may optionally include `tool_allowlist: list[str] | None`.
The effective allowlist is computed on the server:
$$\text{EffectiveToolAllowlist} = \text{ServerRegisteredTools} \cap \text{ClientRequestedTools}$$
If the client requests a tool not registered on the server, it is discarded. The client can only narrow available capabilities, never expand them.

### 5. Execution Scheduling & In-Memory Store
In Slice 6.5, execution is managed in-process via `asyncio.create_task` coordinated by `InMemoryRunStore`:
- `runs: dict[UUID, AgentRun]`
- `cancellation_tokens: dict[UUID, asyncio.Event]`
- `tasks: dict[UUID, asyncio.Task[None]]`
- `event_buffers: dict[UUID, list[SSEEvent]]`

**Explicit Operational Limitations of Single-Process Scheduling**:
1. **Process Restart**: Process restart or worker crash terminates in-flight execution and clears in-memory state.
2. **Process-Local Event Buffers**: SSE event buffers reside in process memory; clients must connect to the process hosting the run.
3. **Single Worker Only**: Running multiple independent worker processes without shared state is not supported in Slice 6.5.
4. **Horizontal Scaling & Crash Durability**: Durable multi-node execution and distributed event broadcasting require a future architecture decision (e.g. Redis / Platform API state sync).

### 6. Server-Sent Events (SSE) Protocol as Observation Projection
SSE events are formatted strictly according to the W3C EventSource standard:
```
id: <sequential_id>
event: <event_name>
data: <json_payload>

```

Standard Event Names:
1. `run.created`: Initial dispatch metadata.
2. `run.started`: Transition to `RUNNING`.
3. `step.started`: Start of reasoning step iteration.
4. `model.delta`: Incremental text token delta.
5. `tool.started`: Tool invocation initiated.
6. `tool.completed`: Tool execution completed.
7. `citation.added`: Provenance citation registered (14 fields).
8. `run.completed`: Final answer and citation list.
9. `run.failed`: Error code and message.
10. `run.cancelled`: Cancellation confirmed.
11. `run.timed_out`: Step or duration budget timeout.

### 7. Event Buffering & Replay
Each run maintains a bounded in-memory event buffer. When an SSE client connects:
1. All prior buffered events are replayed in order (or starting from `Last-Event-ID`).
2. Live events are streamed via an `asyncio.Queue` listener.
3. Upon receiving a terminal event (`run.completed`, `run.failed`, `run.cancelled`, `run.timed_out`), the stream closes cleanly.

## Consequences

### Positive
- Strict cryptographic authentication prevents identity spoofing.
- Public client schemas cannot supply internal capability tokens.
- Standard W3C Server-Sent Events supported natively by browsers without WebSockets.
- Zero external broker dependencies (no Redis, Kafka, Celery required).
- Full compatibility with the 8-state `AgentRun` state machine and 14-field citation evidence contract.

### Explicit Limitations
- In-process execution is single-process and ephemeral; crash durability is not provided in this slice.
