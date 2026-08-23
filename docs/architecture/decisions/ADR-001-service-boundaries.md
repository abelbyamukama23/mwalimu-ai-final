# ADR-001: Service Boundaries

## Status

Accepted

## Context

Mwalimu needs a clear boundary between the system of record and the agent runtime. We must decide which responsibilities belong to which service and how they communicate.

## Decision

We will split the system into two primary runtime services:

1. **Platform API (Django + DRF)** — owns the system of record.
2. **Agent Service (FastAPI)** — owns the agent runtime and tool exposure.

### Platform API responsibilities

- Multi-tenant library model.
- Users, roles, and permissions.
- Connectors, connections, and resources.
- Orchestration metadata for agent sessions and tasks.
- Asynchronous ingestion, embedding generation, and indexing via Celery.
- Vector data stored in PostgreSQL using `pgvector`.
- Original resource files stored in object storage.

### Agent Service responsibilities

- Run agents via the OpenAI Agents SDK.
- Expose native Mwalimu tools.
- Integrate external tools via the MCP client layer.
- Receive context, documents, and state from the Platform API through explicit APIs or MCP-provided resources.

### Key constraints

- The Agent Service **must not directly access PostgreSQL**.
- Communication from the Agent Service to the Platform API uses explicit HTTP APIs or MCP resources.
- Celery workers and Redis are part of the Platform API's asynchronous processing layer.

## Consequences

### Positive

- Clear ownership of data and behavior.
- The Agent Service can be scaled independently from the Platform API.
- The Platform API can evolve its schema and storage without coupling the agent runtime to PostgreSQL.
- Authorization and multi-tenancy remain centralized in the system of record.

### Negative

- Additional network calls between Agent Service and Platform API.
- Need to design stable internal APIs or MCP resources to avoid tight coupling.

## Alternatives Considered

- **Single monolithic Django application running agents.** Rejected because the agent runtime (OpenAI Agents SDK) and MCP integration naturally fit a FastAPI service, and we want independent scalability.
- **Agent Service directly querying PostgreSQL.** Rejected because it breaks the system-of-record boundary, couples the Agent Service to Django's schema, and complicates authorization enforcement.

## Related Decisions

- Vector storage uses PostgreSQL + `pgvector`, managed by the Platform API.
- Object storage holds original resource files, managed by the Platform API.
- MCP is the integration protocol; Streamable HTTP is the preferred remote transport.
