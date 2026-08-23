# Mwalimu — Agent Guidelines

This document encodes the engineering principles, service boundaries, and conventions for the Mwalimu repository.

## Tech Stack

| Concern | Choice |
|--------|--------|
| Platform API | Django + Django REST Framework (DRF) |
| Agent Service | Independent FastAPI service |
| Agent runtime | OpenAI Agents SDK |
| Agent protocol | MCP (Model Context Protocol) |
| Preferred remote MCP transport | Streamable HTTP |
| System of record | PostgreSQL |
| Vector store (initial) | pgvector |
| Asynchronous processing | Celery + Redis |
| Original resource files | Object storage |
| LLM routing | Model Gateway (provider-neutral) |

## Service Boundaries

- **Platform API (Django + DRF)** owns the system of record, multi-tenant library model, users, permissions, connectors, resources, and business/application orchestration.
- **Agent Service (FastAPI)** owns agent orchestration and agent execution. It runs agents via the OpenAI Agents SDK, exposes tools, and is consumed through MCP.
- **The Platform API must never contain the agent loop.** Agent loop logic belongs in the Agent Service.
- **The Agent Service must never become the system of record.** Persistent domain state is owned by the Platform API; the Agent Service receives context, documents, and state through explicit APIs or MCP-provided resources.
- **Agent Service must not directly access PostgreSQL.** It receives context, documents, and state through explicit APIs or MCP-provided resources.
- **Celery workers** handle ingestion, embedding generation, background indexing, and other asynchronous Platform API work.
- **Redis** backs Celery and may be used for ephemeral state such as job locks and result backends.

### Service Boundary Clarification

- **Platform API owns business/application orchestration.** It is the system of record and the orchestrator of business workflows; it must never contain the agent loop.
- **Agent Service owns agent orchestration and agent execution.** It runs the agent loop, exposes tools, and is consumed through MCP; it must never become the system of record.

## Domain Axioms

- A **Library** is a logical knowledge and security boundary, not a deployment boundary.
- There is **no vector database per library**.
- There is **no embedding service per library**.
- **Discovery is not authorization.** A tool or resource being discoverable does not grant permission to use it.
- **LLM behavior is not authorization.** The model cannot grant access; authorization is enforced in code.
- **Connector != Connection != Library.**
  - A `Connector` is a reusable definition of how to reach an external system.
  - A `Connection` is an instantiated, authenticated link scoped to a library.
  - A `Library` is the workspace that owns resources and authorizations.
- **Native Mwalimu tools are not external MCP tools.** Native tools are implemented inside the Agent Service. External MCP tools are provided by third-party MCP servers and invoked through the MCP client layer.

## Architectural Principles

- **Modular services with independent scalability.** Platform API, Agent Service, Celery workers, and Redis can scale independently based on load profile.
- **No microservices unless justified.** Prefer modular monoliths and well-defined internal boundaries until operational or team scale demands a split.
- **DRY** — do not duplicate concepts, validation logic, or domain rules.
- **YAGNI** — do not build speculative abstractions.
- **SOLID** — especially single responsibility for services and clear interfaces.
- **KISS** — prefer the simple, explicit solution.
- **Least privilege** — services and users receive the minimum access required.
- **Fail closed** — when authorization or safety checks cannot complete, deny access by default.
- **Dependency inversion** where justified — depend on abstractions at module boundaries (e.g., model gateway, storage backend), not concrete implementations.
- **Testability** — design for unit, integration, and contract tests from the start.
- **Observability** — expect structured logging, metrics, and tracing at every service boundary.

## Django / PostgreSQL / pgvector

- Use the official **`pgvector`** Python package for Django integration.
- Do **not** use `django-pgvector` or any unofficial wrapper.
- Vector fields, indexes, and similarity queries should be managed explicitly through `pgvector` constructs and Django migrations.

## Repository Layout

```
├── platform_api/        # Django + DRF system of record
├── agent_service/       # FastAPI agent runtime
├── frontend/            # Future web frontend (not implemented)
├── docs/
│   ├── architecture/
│   │   ├── system-architecture.md
│   │   ├── domain-boundaries.md
│   │   └── decisions/
│   │       └── ADR-001-service-boundaries.md
│   └── development/
│       └── local-setup.md
├── .env.example
├── .gitignore
├── AGENTS.md
└── README.md
```

## Current Phase

The foundation phase (Slice 1: Identity/Institution/Membership, Slice 2: Library/Library Access Policy, and Slice 3: Resource/Object Storage) is implemented and under review. Do not implement ingestion, chunking, embeddings, Knowledge Gateway, connectors, the Agent Service runtime, MCP servers, Celery ingestion, or the frontend until the Resource domain is reviewed and the next slice is explicitly authorized.
