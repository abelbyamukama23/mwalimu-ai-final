# ADR-002: Dependency and Runtime Architecture

## Status

Accepted

## Context

The Mwalimu foundation needs a stable, reproducible dependency and runtime architecture. We must choose the Python runtime, web frameworks, vector store, agent runtime, integration protocols, packaging, and health-check conventions.

## Decision

### Runtime

- **Python 3.13** is the runtime for the initial MVP.

### Platform API

- **Django 6.0.x** is the initial web framework.
  - Django 6.1 is deferred because several required ecosystem packages do not yet officially declare Django 6.1 compatibility. We prioritize a stable, fully-supported dependency ecosystem over using the newest framework.
- **Django REST Framework** is used for API endpoints.
- **PostgreSQL** is the system of record.
- **pgvector** is the initial vector store, using the official `pgvector` Python package and the PostgreSQL `pgvector` extension. `django-pgvector` is not used.
- **Celery + Redis** handle asynchronous work such as ingestion, embedding generation, and background indexing.
- **Object storage** holds original resource files.

### Agent Service

- **FastAPI** is the web framework.
- **OpenAI Agents SDK** runs the agent loop.
- The Agent Service receives a scoped `ExecutionContext` from the Platform API.
- An `AgentRun` represents a single agent execution instance.
- The Agent Service does **not** access PostgreSQL directly.

### Service Communication

- **Platform API ↔ Agent Service** uses HTTPS internal application APIs.
- **MCP** is used for:
  - Agent Service ↔ external capabilities.
  - Exposing Mwalimu capabilities to external AI clients.
- **Streamable HTTP** is the preferred remote MCP transport.
- `stdio` is used for local MCP integrations.
- **SSE** is reserved for legacy compatibility only.

### LLM Routing

- The **Model Gateway** is provider-neutral.
- OpenCode Go/Kimi is the development coding environment only; it is **not** Mwalimu's production model provider.

### Identity and Authorization

- The **Platform API** owns identity and authorization.
- The Agent Service receives a scoped `ExecutionContext` and enforces it locally; it does not independently authorize users against the database.

### Packaging

- Each service has its own `pyproject.toml`.
- `uv.lock` files provide reproducible dependency resolution.
- Transitive dependencies are resolved by `uv`; they are not manually pinned.

### Health Architecture

- `/health` reports process liveness.
- `/ready` reports core dependency readiness.
- Capability or provider health is reported separately and must not make the entire service unavailable unnecessarily.

### Excluded Technologies

The following are intentionally not introduced:

- LangChain, LangGraph, LlamaIndex.
- Pinecone.
- Separate vector databases.
- Separate embedding services.
- Kubernetes.
- Unnecessary shared packages.
- Unnecessary microservices.

## Consequences

### Positive

- Reproducible builds through `uv` and `uv.lock`.
- Clear separation of concerns between Platform API and Agent Service.
- The Agent Service is decoupled from PostgreSQL and Django schema details.
- Provider-neutral LLM routing avoids vendor lock-in.
- Standard health endpoints simplify monitoring without over-reporting failures.

### Negative

- Two separate dependency manifests and lock files to maintain.
- Internal HTTPS APIs between services require certificate management in production.
- Deferring Django 6.1 means a future migration when ecosystem support is ready.

## Related Decisions

- ADR-001: Service Boundaries.
- System architecture uses PostgreSQL + `pgvector`, managed by the Platform API.
- Object storage holds original resource files, managed by the Platform API.
