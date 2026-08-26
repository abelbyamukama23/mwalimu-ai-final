# Railway Deployment Guide

Mwalimu is deployed on Railway as **one project (shared environment)** with **four services**
and **two data plugins**. It is a monorepo: each service points at a **Root Directory**
(the app folder), where its `Dockerfile` + `railway.json` live. Railway builds the
`Dockerfile` automatically (it always prefers a Dockerfile).

> This repo already has correct `railway.json` (builder `DOCKERFILE`) per app and
> self-contained Dockerfiles. You just create the services, set root directories, and
> set variables. **You must be logged into GitHub and Railway.**

---

## 1. Create the project + data plugins

1. Railway dashboard → **New Project** (or `railway init`).
2. **New → Database → PostgreSQL** (name: `postgres`). Note the injected `DATABASE_URL`.
3. **New → Database → Redis** (name: `redis`). Note the injected `REDIS_URL`.
4. **Enable pgvector** on the Postgres (Railway Postgres supports it). Run once:
   ```bash
   railway run psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS vector;"
   ```
   (If the plugin image rejects `vector`, use a Postgres image with pgvector and re-point `DATABASE_URL`.)

---

## 2. Add the four services (each with a Root Directory)

| Service | Source (repo) | Root Directory | Build | Start command (set in Service → Settings) |
|---|---|---|---|---|
| `platform-api` | your repo | `platform_api` | Dockerfile (auto) | *(leave default — Dockerfile CMD runs migrate+collectstatic+gunicorn)* |
| `celery-worker` | your repo | `platform_api` | Dockerfile (auto) | `celery -A platform_api worker -Q default,ingestion -l info` |
| `agent-service` | your repo | `agent_service` | Dockerfile (auto) | *(default — Dockerfile CMD runs uvicorn)* |
| `frontend` | your repo | `frontend` | Dockerfile (auto) | *(default — Dockerfile CMD runs next start)* |

> - The **worker** is a plain Service (no Public Networking) with its own start command.
> - The `platform_api` root is shared by `platform-api` and `celery-worker`; both build the same Dockerfile. The web runs the Dockerfile CMD (migrate → collectstatic → gunicorn); the worker overrides the start command to Celery.
> - Because the platform runs `migrate`/`collectstatic` on start (idempotent), no external pre-deploy step is needed.

---

## 3. Variables

Railway injects **`DATABASE_URL`** (Postgres) and **`REDIS_URL`** (Redis) into the project
automatically. The Django app now reads `DATABASE_URL` directly.

Set these on the relevant services (Service → Variables). Railway supports `${{...}}`
variable interpolation.

### `platform-api` and `celery-worker`
| Variable | Value |
|---|---|
| `DATABASE_URL` | (injected by Postgres — no action) |
| `CELERY_BROKER_URL` | `${{redis.REDIS_URL}}` |
| `CELERY_RESULT_BACKEND` | `${{redis.REDIS_URL}}` |
| `DJANGO_SETTINGS_MODULE` | `platform_api.settings` |
| `SECRET_KEY` | a strong random value |
| `DEBUG` | `false` |
| `ALLOWED_HOSTS` | `<platform public host>,<frontend public host>,<agent public host>` |
| `CSRF_TRUSTED_ORIGINS` | `https://<platform host>,https://<frontend host>` |
| `AGENT_SERVICE_BASE_URL` | `https://${{agent-service.PUBLIC_DOMAIN}}` |
| `AGENT_SERVICE_PUBLIC_BASE_URL` | `https://${{agent-service.PUBLIC_DOMAIN}}` |
| `AGENT_SERVICE_JWT_SECRET_KEY` | **same as agent `JWT_SECRET_KEY`** |
| `INTERNAL_SERVICE_SECRET_KEY` | **same as agent `INTERNAL_SERVICE_SECRET_KEY`** |
| `AGENT_STREAM_JWT_SECRET_KEY` | **same as agent `AGENT_STREAM_JWT_SECRET_KEY`** |
| `OBJECT_STORAGE_BACKEND` | `platform_api.apps.resources.storage.S3Storage` |
| `OBJECT_STORAGE_ENDPOINT/REGION/ACCESS_KEY/SECRET_KEY/BUCKET` | your S3-compatible creds |
| `EMBEDDING_PROVIDER_BACKEND` | `platform_api.apps.processing.embedding.openai_provider.OpenAICompatibleProvider` |
| `EMBEDDING_API_KEY` | OpenAI (or compatible) — DeepSeek has no embeddings |
| `EMBEDDING_MODEL` / `EMBEDDING_DIMENSIONS` | `text-embedding-3-small` / `1536` |

### `agent-service`
| Variable | Value |
|---|---|
| `DEFAULT_MODEL_PROVIDER` | `deepseek` |
| `DEEPSEEK_API_KEY` | your DeepSeek key |
| `DEEPSEEK_DEFAULT_MODEL` | `deepseek-chat` |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` |
| `PLATFORM_API_BASE_URL` | `https://${{platform-api.PUBLIC_DOMAIN}}` |
| `PLATFORM_COMPLETION_URL` | `https://${{platform-api.PUBLIC_DOMAIN}}` |
| `JWT_SECRET_KEY` | **same as platform `AGENT_SERVICE_JWT_SECRET_KEY`** |
| `INTERNAL_SERVICE_SECRET_KEY` | **same as platform value** |
| `AGENT_STREAM_JWT_SECRET_KEY` | **same as platform value** |
| `ENVIRONMENT` / `LOG_LEVEL` | `production` / `INFO` |

### `frontend`
| Variable | Value |
|---|---|
| `NEXT_PUBLIC_PLATFORM_API_BASE_URL` | `https://${{platform-api.PUBLIC_DOMAIN}}` (inlined at build; Railway passes it to the build) |

> Replace `platform-api`/`agent-service`/`redis` in the `${{...}}` refs with the actual
> service names you used.

---

## 4. Deploy order

1. Data plugins: PostgreSQL (+pgvector), Redis.
2. `platform-api` (runs migrate on start).
3. `agent-service`.
4. `celery-worker`.
5. `frontend` (needs the platform URL at build).

Each: **Deploy** from the repo. Then verify:

```bash
curl https://agent-service.up.railway.app/health    # {"status":"healthy",...}
# frontend → login → send a prompt → streamed response.
```

---

## 5. Critical flags

- **pgvector** must exist before the knowledge gateway queries (`CREATE EXTENSION IF NOT EXISTS vector;` in the Postgres, or a pgvector-enabled image).
- **Object storage** — no Railway plugin; provide S3-compatible creds or resource upload/ingestion fails (chat works without it).
- **Embeddings** — DeepSeek has no embeddings API; use an OpenAI-compatible key or the knowledge gateway 503s.
- **The 3 shared secrets** must be identical on `platform-api` and `agent-service` or dispatch/completion/SSE break.
- **`NEXT_PUBLIC_*`** is inlined at build — set the frontend variable before its build (deploy the platform first).
- **`railway.json`** (config-as-code) keeps working (until 2026-12-01); the per-service files here only force the Dockerfile builder. If Railway defaults to Railpack anyway, it auto-uses the Dockerfile because one is present.
