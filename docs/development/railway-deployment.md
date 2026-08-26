# Railway Deployment Guide

Mwalimu is deployed to Railway as a **single project (one shared environment)** with
**four services** plus **two managed data plugins**. Every service is built from its own
subdirectory (monorepo) using the committed `Dockerfile` + `railway.json` in each folder.

> You must run the deploy from your own Railway account (`railway login`). The
> Dockerfiles, `.dockerignore`, and `railway.json` in this repo are ready; this guide
> tells you how to wire them and set the variables. Nothing here requires code changes,
> but see **§9 Critical flags** for the few provider/secret decisions only you can make.

---

## 1. Service & resource map

| Railway service | Root directory | Builder | Runs | Protocol |
|---|---|---|---|---|
| `platform-api` (web) | `platform_api` | Dockerfile | gunicorn (Django WSGI) | HTTP |
| `celery-worker` | `platform_api` | Dockerfile (same image) | celery worker | internal |
| `agent-service` | `agent_service` | Dockerfile | uvicorn (FastAPI) | HTTP/SSE |
| `frontend` | `frontend` | Dockerfile | `next start` | HTTP |

Shared plugins: **PostgreSQL** (+ pgvector) and **Redis**.

```
BROWSER → frontend (Next.js) ──REST──▶ platform-api (Django) ──dispatch──▶ agent-service (FastAPI) ──▶ DeepSeek
                                        │   │                              │
                                        │   └── Celery worker (ingestion/indexing)
                                        └─ knowledge gateway ◀── knowledge_search ◀── agent-service
```

---

## 2. Prerequisites

- Railway CLI: `npm i -g @railway/cli` and `railway login`.
- A real **S3-compatible** bucket (AWS S3, Cloudflare R2, or MinIO) — Railway has no object-storage plugin.
- An **OpenAI (or OpenAI-compatible) embeddings API key** — DeepSeek does **not** provide embeddings.
- A **DeepSeek API key** (chat completions only).

---

## 3. Project + data plugins

1. `railway init` (or create a project in the dashboard).
2. **Add PostgreSQL** → plugin. Note the injected vars: `DATABASE_URL`, `PGHOST`, `PGUSER`, `PGPASSWORD`, `PGPORT`, `PGDATABASE`.
3. **Enable pgvector** (required by the knowledge gateway). Connect and run once:
   ```bash
   railway run psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS vector;"
   ```
   If Railway's Postgres image lacks the extension, use a Postgres image with pgvector
   (e.g. `pgvector/pgvector:pg16`) as a custom service (see §9).
4. **Add Redis** → plugin. Note `REDIS_URL`.

---

## 4. Create the four services

For each: **Root Directory** = the service folder, **Builder** = Dockerfile.

| Service | Root Directory | Start command (override if different) | Pre-deploy |
|---|---|---|---|
| `platform-api` | `platform_api` | *(use `railway.json`)* | `migrate` + `collectstatic` (from `railway.json`) |
| `celery-worker` | `platform_api` | `sh -c ".venv/bin/celery -A platform_api worker -Q default,ingestion -l info"` | *(railway.json idempotent migrate — safe)* |
| `agent-service` | `agent_service` | *(use `railway.json`)* | — |
| `frontend` | `frontend` | *(use `railway.json`)* | — |

> Django `migrate` is idempotent, so the worker also running it is safe.

---

## 5. Shared (project-level) variables

Set these once in the project Variables so all services see them:

| Variable | Value |
|---|---|
| `DATABASE_NAME` | `${{Postgres.PGDATABASE}}` |
| `DATABASE_USER` | `${{Postgres.PGUSER}}` |
| `DATABASE_PASSWORD` | `${{Postgres.PGPASSWORD}}` |
| `DATABASE_HOST` | `${{Postgres.PGHOST}}` |
| `DATABASE_PORT` | `${{Postgres.PGPORT}}` |
| `CELERY_BROKER_URL` | `${{Redis.REDIS_URL}}` |
| `CELERY_RESULT_BACKEND` | `${{Redis.REDIS_URL}}` |

(If Railway names the plugin differently, substitute that reference name.)

---

## 6. Per-service variables

### `platform-api`
| Variable | Value | Notes |
|---|---|---|
| `SECRET_KEY` | `<strong random>` | |
| `DEBUG` | `False` | |
| `ALLOWED_HOSTS` | `<platform domain>,<agent domain>,<frontend domain>` | comma-separated |
| `CSRF_TRUSTED_ORIGINS` | `https://<platform>,https://<frontend>` | |
| `CORS_ALLOWED_ORIGINS` | `https://<frontend>` | |
| `CSRF_COOKIE_SECURE` / `REFRESH_COOKIE_SECURE` | `True` | HTTPS only |
| `AGENT_SERVICE_BASE_URL` | `https://${{agent-service.PUBLIC_DOMAIN}}` | platform→agent dispatch |
| `AGENT_SERVICE_PUBLIC_BASE_URL` | `https://${{agent-service.PUBLIC_DOMAIN}}` | used to build the SSE URL the browser opens |
| `AGENT_SERVICE_JWT_SECRET_KEY` | **must equal** agent `JWT_SECRET_KEY` | |
| `INTERNAL_SERVICE_SECRET_KEY` | **must equal** agent `INTERNAL_SERVICE_SECRET_KEY` | Domain D completion |
| `AGENT_STREAM_JWT_SECRET_KEY` | **must equal** agent `AGENT_STREAM_JWT_SECRET_KEY` | Domain S stream tickets |
| `OBJECT_STORAGE_BACKEND` | `platform_api.apps.resources.storage.S3Storage` | |
| `OBJECT_STORAGE_ENDPOINT` / `REGION` / `ACCESS_KEY` / `SECRET_KEY` / `BUCKET` | your S3 creds | |
| `EMBEDDING_PROVIDER_BACKEND` | (`openai` default) | |
| `EMBEDDING_API_KEY` | your OpenAI (or compatible) key | DeepSeek has no embeddings |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | must match `EMBEDDING_DIMENSIONS` (1536) |

### `celery-worker`
Same as `platform-api` (it uses the same image + settings). Ensure `CELERY_BROKER_URL`
is set (already in shared vars).

### `agent-service`
| Variable | Value | Notes |
|---|---|---|
| `ENVIRONMENT` | `production` | |
| `LOG_LEVEL` | `INFO` | |
| `DEFAULT_MODEL_PROVIDER` | `deepseek` | |
| `DEEPSEEK_API_KEY` | your DeepSeek key | |
| `DEEPSEEK_DEFAULT_MODEL` | `deepseek-chat` | |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` | |
| `PLATFORM_API_BASE_URL` | `https://${{platform-api.PUBLIC_DOMAIN}}` | agent→knowledge gateway |
| `PLATFORM_COMPLETION_URL` | `https://${{platform-api.PUBLIC_DOMAIN}}` | Domain D callback |
| `JWT_SECRET_KEY` | **must equal** platform `AGENT_SERVICE_JWT_SECRET_KEY` | |
| `INTERNAL_SERVICE_SECRET_KEY` | **must equal** platform `INTERNAL_SERVICE_SECRET_KEY` | |
| `AGENT_STREAM_JWT_SECRET_KEY` | **must equal** platform `AGENT_STREAM_JWT_SECRET_KEY` | |

### `frontend`
| Variable | Value | Notes |
|---|---|---|
| `NEXT_PUBLIC_PLATFORM_API_BASE_URL` | `https://${{platform-api.PUBLIC_DOMAIN}}` | **inlined at build** — set before build |

---

## 7. Deploy order

1. Data plugins (Postgres+pgvector, Redis).
2. `platform-api` (runs migrations).
3. `agent-service`.
4. `celery-worker`.
5. `frontend` (last — needs the platform URL at build time).

Then:
```bash
railway up        # per service, from that service's directory, or use the dashboard Deploy button
```

---

## 8. Verify

- `platform-api` → `GET /api/v1/auth/login/` returns 200 (OPTIONS/405) → not 5xx.
- `agent-service` → `GET /health` returns `{"status":"healthy",...}`.
- `frontend` → loads the login page; login → new chat → send a prompt → streamed response appears.
- In the Platform API app, apply migrations first (pre-deploy does this).
- Confirm the browser can reach the agent's SSE URL (`AGENT_SERVICE_PUBLIC_BASE_URL`) cross-origin (agent CORS is `*`).

---

## 9. Critical flags (decisions only you can make)

1. **pgvector on Railway Postgres.** The managed Postgres image may not ship pgvector. Preferred: run
   `CREATE EXTENSION IF NOT EXISTS vector;` once. If unavailable, use a custom Postgres service from
   `pgvector/pgvector:pg16` (set its `DATABASE_*`/`DATABASE_URL` into the shared vars). Without pgvector,
   the knowledge/indexing queries fail.
2. **Object storage (S3).** No Railway plugin. Provide S3-compatible creds or resource **upload** and any
   storage-backed ingestion fail (chat/auth still work). Set `OBJECT_STORAGE_*` accordingly.
3. **Embeddings.** DeepSeek does **not** expose an embeddings API. Use an OpenAI/compatible embeddings key
   (`EMBEDDING_API_KEY`) or the knowledge gateway will 503. `EMBEDDING_MODEL`/`EMBEDDING_DIMENSIONS` must
   match the values used at index time.
4. **Secret sync.** The three pairs in §6 must match exactly or dispatch/auth/SSE break:
   `JWT_SECRET_KEY`↔`AGENT_SERVICE_JWT_SECRET_KEY`, `INTERNAL_SERVICE_SECRET_KEY`↔`INTERNAL_SERVICE_SECRET_KEY`,
   `AGENT_STREAM_JWT_SECRET_KEY`↔`AGENT_STREAM_JWT_SECRET_KEY`.
5. **NEXT_PUBLIC inlining.** The frontend build bakes `NEXT_PUBLIC_PLATFORM_API_BASE_URL`. Deploy
   `platform-api` first, copy its public domain into the frontend service, then build/deploy the frontend.
   If that domain changes later, re-deploy the frontend.
6. **Healthcheck for `platform-api`.** The Django app has no `/health` route, so its `railway.json`
   omits a healthcheck path. Railway will still deploy/keep it alive; add a tiny `GET /health/` view
   (a ~5-line infra-only addition) if you want an active probe.
7. **`RUN` migrations once.** Pre-deploy runs `migrate` + `collectstatic` idempotently. First deploy is
   where the schema is created.

---

## 10. Notes

- Seeded/static data: no seed migrations exist for PG regions/knowledge; the resolver returns empty
  context until `GeographicUnit`/`ContextResource` rows exist (create via a data migration or `manage.py shell`).
- The agent service has no database access; it only calls the Platform API (correct per architecture).
- For a truly production hardening pass (rate limits, worker scale, object storage lifecycle, observability),
  that is separate from this go-live setup.
