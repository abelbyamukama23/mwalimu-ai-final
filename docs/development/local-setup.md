# Local Setup

This guide covers the local development environment for the Mwalimu foundation.

## Approved Dependency/Runtime Decisions

- **Python 3.13** is the runtime for the initial MVP.
- **Django 6.0.x** is used for the Platform API. Django 6.1 is deferred until the ecosystem officially declares compatibility.
- **Django REST Framework** is used for the Platform API.
- **FastAPI** is used for the Agent Service.
- **OpenAI Agents SDK** runs the agent loop in the Agent Service.
- **MCP** is used for Agent Service ↔ external capabilities and for exposing Mwalimu capabilities to external AI clients.
- **Streamable HTTP** is the preferred remote MCP transport. `stdio` is for local integrations. SSE is for legacy compatibility only.
- **PostgreSQL + pgvector** is the system of record and initial vector store. The official `pgvector` Python package and PostgreSQL `pgvector` extension are used. `django-pgvector` is not used.
- **Celery + Redis** handle asynchronous Platform API work.
- **Object storage** holds original resource files.
- **HTTPS internal application APIs** connect the Platform API and Agent Service.
- **pyproject.toml** per service and **uv.lock** provide reproducible dependency resolution. Transitive dependencies are resolved by `uv`, not manually pinned.
- **Model Gateway** remains provider-neutral.
- **OpenCode Go/Kimi** is the development coding environment only; it is not the production model provider.
- **Platform API** owns identity and authorization. The Agent Service receives a scoped `ExecutionContext` and must not access PostgreSQL directly.

Intentionally excluded:

- LangChain, LangGraph, LlamaIndex.
- Pinecone or separate vector databases.
- Separate embedding services.
- Kubernetes.
- Unnecessary shared packages or microservices.

## Prerequisites

- Python 3.13
- `uv` package manager
- PostgreSQL 15+ with the `pgvector` extension installed
- Redis 7+
- Git
- (Optional) Docker and Docker Compose for running PostgreSQL, Redis, and object storage

## Repository structure

```
├── platform_api/        # Django + DRF system of record
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── src/
│   └── tests/
├── agent_service/       # FastAPI agent runtime
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── src/
│   └── tests/
├── frontend/            # Future web frontend (not implemented)
├── docs/
├── .env.example
├── .gitignore
├── AGENTS.md
└── README.md
```

## Environment

1. Copy the example environment file:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` to match your local PostgreSQL, Redis, and object storage configuration.

## Python

Install Python 3.13 with `uv`:

```bash
uv python install 3.13
```

## PostgreSQL

Create a local database and enable the `pgvector` extension:

```sql
CREATE DATABASE mwalimu;
CREATE USER mwalimu WITH PASSWORD 'mwalimu';
GRANT ALL PRIVILEGES ON DATABASE mwalimu TO mwalimu;

\c mwalimu
CREATE EXTENSION IF NOT EXISTS vector;
```

Use the official `pgvector` Python package for Django integration. Do not install `django-pgvector`.

## Redis

Start Redis locally:

```bash
redis-server
```

The default configuration expects Redis at `redis://localhost:6379/0`.

## Object storage

Use MinIO or another S3-compatible store for original resource files. Update `.env` with the endpoint, credentials, and bucket name.

## Platform API

1. Change into the service directory:

   ```bash
   cd platform_api
   ```

2. Create a virtual environment and install dependencies from `pyproject.toml`:

   ```bash
   uv sync
   ```

3. Activate the environment and run checks:

   ```bash
   uv run pytest
   uv run ruff check .
   uv run mypy src
   ```

4. When implemented, run migrations and start the Django development server:

   ```bash
   uv run python src/manage.py migrate
   uv run python src/manage.py runserver
   ```

## Agent Service

1. Change into the service directory:

   ```bash
   cd agent_service
   ```

2. Create a virtual environment and install dependencies from `pyproject.toml`:

   ```bash
   uv sync
   ```

3. Activate the environment and run checks:

   ```bash
   uv run pytest
   uv run ruff check .
   uv run mypy src
   ```

4. When implemented, start the FastAPI development server:

   ```bash
   uv run uvicorn agent_service.main:app --reload
   ```

## Celery workers

Celery workers are not yet implemented. When implemented, start them from the Platform API project:

```bash
cd platform_api
uv run celery -A platform_api worker -l info
```

## Notes

- Do not implement Django models, migrations, runtime dependencies, FastAPI endpoints, MCP servers, or the frontend until the foundation artifacts are complete and reviewed.
- Keep service dependencies explicit and documented in per-service `pyproject.toml` files.
- Resolve dependencies with `uv` and commit the generated `uv.lock` files for reproducible builds.
