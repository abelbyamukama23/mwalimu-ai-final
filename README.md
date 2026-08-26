# Mwalimu

Mwalimu is a multi-tenant knowledge and agent platform.

## Overview

The platform is split into independent services with well-defined responsibilities:

- **Platform API** (`platform_api/`): Django + Django REST Framework. Owns the system of record, multi-tenant library model, users, permissions, connectors, resources, and orchestration metadata.
- **Agent Service** (`agent_service/`): FastAPI service that runs agents via the OpenAI Agents SDK, exposed through MCP.
- **Celery workers**: Handle ingestion, embedding generation, background indexing, and other asynchronous work.
- **Frontend** (`frontend/`): Next.js 16 + TypeScript + Tailwind CSS v4 web frontend. Phase 0 foundation (design tokens, primitives, shells, and the `/chat/new` screen) is in place; feature wiring follows in later phases.

## Documentation

- [System Architecture](docs/architecture/system-architecture.md)
- [Domain Boundaries](docs/architecture/domain-boundaries.md)
- [ADR-001: Service Boundaries](docs/architecture/decisions/ADR-001-service-boundaries.md)
- [ADR-002: Dependency and Runtime Architecture](docs/architecture/decisions/ADR-002-dependency-runtime-architecture.md)
- [ADR-003: Extraction Library Selection](docs/architecture/decisions/ADR-003-extraction-library-selection.md)
- [ADR-004: Embedding Provider Boundary](docs/architecture/decisions/ADR-004-embedding-provider-boundary.md)
- [ADR-005: Chunking Strategy and Provenance Fields](docs/architecture/decisions/ADR-005-chunking-strategy-provenance.md)
- [ADR-006: pgvector Schema and Indexing](docs/architecture/decisions/ADR-006-pgvector-schema-indexing.md)
- [ADR-007: Processing Identity, Idempotency, and Versioned Embeddings](docs/architecture/decisions/ADR-007-processing-identity-idempotency.md)
- [ADR-008: Celery Pipeline Topology](docs/architecture/decisions/ADR-008-celery-pipeline-topology.md)
- [Local Setup](docs/development/local-setup.md)
- [Agent Guidelines](AGENTS.md)

## Status

Slice 1 (Identity + Institution + Membership), Slice 2 (Library + Library Access Policy), Slice 3 (Resource + Object Storage), and Slice 4 (Document Processing + Knowledge Indexing) are implemented in the Platform API.

