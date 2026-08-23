# Mwalimu

Mwalimu is a multi-tenant knowledge and agent platform.

## Overview

The platform is split into independent services with well-defined responsibilities:

- **Platform API** (`platform_api/`): Django + Django REST Framework. Owns the system of record, multi-tenant library model, users, permissions, connectors, resources, and orchestration metadata.
- **Agent Service** (`agent_service/`): FastAPI service that runs agents via the OpenAI Agents SDK, exposed through MCP.
- **Celery workers**: Handle ingestion, embedding generation, background indexing, and other asynchronous work.
- **Frontend** (`frontend/`): Future web frontend. Not implemented in the current phase.

## Documentation

- [System Architecture](docs/architecture/system-architecture.md)
- [Domain Boundaries](docs/architecture/domain-boundaries.md)
- [ADR-001: Service Boundaries](docs/architecture/decisions/ADR-001-service-boundaries.md)
- [ADR-002: Dependency and Runtime Architecture](docs/architecture/decisions/ADR-002-dependency-runtime-architecture.md)
- [Local Setup](docs/development/local-setup.md)
- [Agent Guidelines](AGENTS.md)

## Status

Slice 1 (Identity + Institution + Membership), Slice 2 (Library + Library Access Policy), and Slice 3 (Resource + Object Storage) implemented in the Platform API. Waiting for review before proceeding to ingestion, chunking, embeddings, Knowledge Gateway, Agent Service, or MCP.
