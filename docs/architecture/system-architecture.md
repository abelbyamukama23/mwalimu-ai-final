# System Architecture

This document describes the high-level architecture of the Mwalimu platform.

## Context

Mwalimu is a multi-tenant knowledge and agent platform. The system is split into independent services with explicit responsibilities, but it does not adopt microservices for their own sake.

## Services

```
┌─────────────────────────────────────────────────────────────────────┐
│                              Clients                                │
│            (web frontend, CLI, third-party integrations)            │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                │ HTTP / MCP
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Agent Service                               │
│                       FastAPI + OpenAI Agents SDK                   │
│                                                                     │
│   • Runs agent turns                                                │
│   • Exposes native Mwalimu tools                                    │
│   • Integrates external tools via MCP client                        │
│   • Receives context/state via Platform API                         │
│   • Receives a scoped ExecutionContext; does not access PostgreSQL  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                │ Internal HTTPS application APIs
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Platform API                                │
│                    Django + Django REST Framework                   │
│                                                                     │
│   • System of record (libraries, users, permissions, resources)     │
│   • Connectors and connections                                      │
│   • Orchestration metadata                                          │
│   • Vector storage via PostgreSQL + pgvector                        │
│   • Object storage for original resource files                      │
│   • Owns identity and authorization                                 │
└───────────────────────┬───────────────────────┬─────────────────────┘
                        │                       │
                        │ Asynchronous work     │ Ephemeral state
                        ▼                       ▼
              ┌─────────────────┐     ┌─────────────────┐
              │  Celery workers │     │      Redis      │
              │                 │     │                 │
              │ • Ingestion     │     │ • Broker        │
              │ • Embeddings    │     │ • Result backend│
              │ • Indexing      │     │ • Job locks     │
└─────────────────┘     └─────────────────┘
```

## Platform API (Django + DRF)

The Platform API owns:

- Multi-tenant library model.
- Users, roles, and permissions.
- Connector definitions and library-scoped connections.
- Resources and their metadata.
- Orchestration metadata for agent sessions and tasks.
- Vector search data stored in PostgreSQL via the official `pgvector` Python package and PostgreSQL `pgvector` extension.
- Object storage for original resource files.
- Identity and authorization.

It does **not** run agents directly.

## Agent Service (FastAPI + OpenAI Agents SDK)

The Agent Service:

- Runs agent turns using the OpenAI Agents SDK.
- Exposes native Mwalimu tools implemented inside the service.
- Integrates external tools through the MCP client layer.
- Communicates with the Platform API for context, documents, and state via HTTPS internal application APIs.
- Receives a scoped `ExecutionContext` from the Platform API.
- Tracks work through `AgentRun` instances.
- Does **not** access PostgreSQL directly.

## Asynchronous Processing

Celery workers perform long-running or background tasks:

- Ingesting uploaded or connected resources.
- Generating embeddings.
- Background indexing and re-indexing.
- Other asynchronous Platform API work.

Redis backs Celery and may be used for ephemeral state such as job locks and result backends.

## Storage

- **PostgreSQL** is the system of record.
- **pgvector** is the initial vector store, accessed through the official `pgvector` Python package and the PostgreSQL `pgvector` extension.
- **Object storage** holds original resource files.

There is no vector database per library and no embedding service per library.

## Model Gateway

A provider-neutral model gateway routes LLM requests. The gateway abstraction keeps the Agent Service decoupled from any single LLM provider. The Agent Service uses the gateway through a provider-neutral interface; OpenCode Go/Kimi is the development coding environment only and is not Mwalimu's production model provider.

## Integration Protocol

MCP is the integration protocol for:

- Agent Service ↔ external capabilities.
- Exposing Mwalimu capabilities to external AI clients.

The preferred remote MCP transport is **Streamable HTTP**. `stdio` is used for local integrations. **SSE** is reserved for legacy compatibility only.

Platform API ↔ Agent Service communication uses HTTPS internal application APIs, not MCP.

## Health Architecture

Each service exposes standard health endpoints:

- `/health` — process liveness. Returns 200 when the process is running.
- `/ready` — core dependency readiness. Returns 200 only when required core dependencies (e.g., database, Redis) are reachable and usable.

Capability or provider health is reported separately and must not make the entire service unavailable unnecessarily.

## Scalability

Platform API, Agent Service, Celery workers, and Redis can scale independently based on their load profiles. Services are modular but not prematurely split into microservices.

## Technology Constraints

The following are intentionally excluded from the architecture:

- LangChain, LangGraph, LlamaIndex.
- Pinecone or separate vector databases.
- Separate embedding services.
- Kubernetes.
- Unnecessary shared packages or microservices.
