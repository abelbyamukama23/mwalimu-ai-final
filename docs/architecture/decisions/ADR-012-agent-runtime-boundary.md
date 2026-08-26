# ADR-012: Agent Runtime Boundary

## Status

Accepted (Design Phase — Slice 6)

## Context

Mwalimu requires an intelligent, multi-step agentic execution runtime capable of reasoning, planning, selecting tools, invoking LLM providers, and executing capabilities on behalf of users.

Per [ADR-001](ADR-001-service-boundaries.md) and [`AGENTS.md`](../../AGENTS.md), the system of record belongs strictly in the Platform API (Django), while agent execution and orchestration belong in the Agent Service (FastAPI). We must define the formal boundary of the Agent Execution Runtime: what it owns, what it does not own, and how it interacts with external capabilities.

## Decision

We establish the **Agent Execution Runtime** as an autonomous, decoupled execution engine inside the `agent_service/` application.

### 1. Responsibilities of the Agent Execution Runtime

- **Agent Reasoning Loop**: Managing multi-turn reasoning, tool call evaluation, output synthesis, and termination.
- **AgentRun Lifecycle**: Managing the state machine, timeouts, step limits, and cancellation of individual execution runs.
- **Model Gateway / Provider Abstraction**: Routing prompts to LLM providers (OpenAI, Gemini, DeepSeek, etc.) via a unified protocol without provider leakage.
- **Capability / Tool Registry**: Exposing native tools, Knowledge Gateway client capabilities, and external MCP tools under a uniform execution interface.
- **Context & Working Memory Management**: Managing working scratchpads, conversation history windows, and evidence citations.
- **Execution Policy Enforcement**: Enforcing step budgets, token budgets, execution timeouts, and tool allowlists.
- **Observability & Audit Streaming**: Emitting structured lifecycle events, step traces, and SSE streams for client visibility.

### 2. Explicit Non-Responsibilities (Prohibitions)

- **System of Record**: The Agent Runtime never persists persistent domain entities (users, institutions, libraries, resources).
- **Direct Database Access**: The Agent Runtime **must never directly access PostgreSQL or pgvector**.
- **Authorization Authority**: The Agent Runtime cannot grant, expand, or evaluate institutional permissions. All capability invocations are authenticated using delegated execution credentials validated by the capability providers.
- **Ingestion & Indexing**: The Agent Runtime does not extract, chunk, embed, or index documents; it consumes retrieval via the Knowledge Gateway.

## Consequences

### Positive

- Complete decoupling between LLM reasoning and the system-of-record schema.
- Agent Service can scale horizontally and independently from the Platform API.
- Clear separation of concerns: Agent decides *what* capability to invoke; capability providers decide *how* authorization is enforced.
- Prompt injection cannot compromise platform authorization because the model has no path to elevate server-side permissions.

### Negative

- Inter-service network communication required to retrieve knowledge or report execution results to the Platform API.
- Need for robust distributed cancellation and timeout propagation across service boundaries.

## Related Decisions

- [ADR-001: Service Boundaries](ADR-001-service-boundaries.md)
- [ADR-009: Knowledge Gateway Placement](ADR-009-knowledge-gateway-placement.md)
- [ADR-010: Retrieval Authorization Model](ADR-010-retrieval-authorization-model.md)
- [ADR-013: AgentRun State Machine](ADR-013-agentrun-state-machine.md)
- [ADR-014: Execution Context & Identity](ADR-014-execution-context-and-identity.md)
