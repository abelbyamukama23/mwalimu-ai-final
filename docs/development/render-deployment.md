# Render Deployment Guide

Mwalimu is deployed on **Render** as a **monorepo Blueprint**: one repo, many services,
each built from its own root directory. Push the repo to GitHub, then have Render
import it as a Blueprint.

> The Dockerfiles + `railway.json` + `render.yaml` are committed. This guide is the
> operational wrapper. **You must be logged into GitHub and Render.**

---

## 1. Push to GitHub

```bash
cd mwalimu_final
git add -A
git commit -m "feat: Mwalimu platform — deployable multi-service monorepo"
git branch -M main
git remote add origin https://github.com/<you>/mwalimu.git   # create the repo first
git push -u origin main
```

No `gh` CLI here, so create the repo on github.com (or `winget install GitHub.cli`, then
`gh repo create mwalimu --private --source=. --push`).

---

## 2. Create the Render Blueprint

1. Render dashboard → **New + Blueprint** → select the GitHub repo.
2. Render reads `render.yaml` and proposes: `mwalimu-platform-api`, `mwalimu-celery-worker`,
   `mwalimu-agent-service`, `mwalimu-frontend`, `mwalimu-postgres`, `mwalimu-redis`.
3. **Before applying**, set real values for the blanks in the dashboard (see §4).

---

## 3. What the Blueprint creates

| Service | Type | Root | Command | Notes |
|---|---|---|---|---|
| `mwalimu-platform-api` | web | `platform_api` | gunicorn | pre-deploy: `CREATE EXTENSION vector`, `migrate`, `collectstatic`; `/` root (add `/health/` if you want a probe) |
| `mwalimu-celery-worker` | worker | `platform_api` | `celery -A platform_api worker -Q default,ingestion` | background ingestion/indexing |
| `mwalimu-agent-service` | web | `agent_service` | uvicorn | healthcheck `/health` |
| `mwalimu-frontend` | web | `frontend` | `next start` | needs the platform URL baked in |
| `mwalimu-postgres` | postgres | — | — | pgvector enabled in pre-deploy |
| `mwalimu-redis` | redis | — | — | broker/result backend |

---

## 4. Fill in secrets/providers (dashboard)

These are intentionally **empty or placeholder** in `render.yaml`; the Blueprint will
fail or misbehave until set:

| Where | Variable | Set to |
|---|---|---|
| platform + worker | `OBJECT_STORAGE_ACCESS_KEY/SECRET_KEY`, `OBJECT_STORAGE_ENDPOINT`, `OBJECT_STORAGE_REGION` | your S3-compatible creds (S3/R2/MinIO) |
| platform + worker | `EMBEDDING_API_KEY` | an OpenAI (or compatible) embeddings key |
| agent | `DEEPSEEK_API_KEY` | your DeepSeek key |
| platform + agent | `AGENT_SERVICE_JWT_SECRET_KEY` / `JWT_SECRET_KEY` | **same** strong value on both |
| platform + agent | `INTERNAL_SERVICE_SECRET_KEY` | **same** value on both |
| platform + agent | `AGENT_STREAM_JWT_SECRET_KEY` | **same** value on both |

> **Critical:** the three paired secrets must be identical on the Platform and Agent or
> dispatch, Domain-D completion, and SSE streaming all fail.

---

## 5. Deploy order + notes

- Apply the Blueprint once. Render creates the DB + Redis and deploys the four services.
- The platform's pre-deploy runs `CREATE EXTENSION IF NOT EXISTS vector;` then `migrate`.
- Deploy the **frontend last** (or rebuild it) once the platform's public URL is fixed,
  since `NEXT_PUBLIC_PLATFORM_API_BASE_URL` is inlined at build.
- **Verify the `RENDER_EXTERNAL_URL` property** used for cross-service URLs; if Render
  denies it, set `AGENT_SERVICE_BASE_URL`, `AGENT_SERVICE_PUBLIC_BASE_URL`,
  `PLATFORM_API_BASE_URL`, `PLATFORM_COMPLETION_URL`, and `NEXT_PUBLIC_PLATFORM_API_BASE_URL`
  manually to `https://<service>.onrender.com` and redeploy.

---

## 6. Verify

```bash
curl https://mwalimu-agent-service.onrender.com/health     # {"status":"healthy",...}
# logs in via the frontend; send a prompt; confirm streaming + persistence.
```

---

## 7. Flags (host-independent)

- **pgvector** must exist in the Postgres before migrations that use it; the pre-deploy
  command handles it. If the Postgres image rejects the extension, provision a server
  with pgvector and re-point `DATABASE_*`.
- **Object storage** has no managed plugin — use an S3-compatible bucket or resource
  upload/ingestion fails (chat/auth still work).
- **Embeddings** — DeepSeek has no embeddings API; provide an OpenAI key or knowledge
  retrieval 503s. `EMBEDDING_MODEL` must match `EMBEDDING_DIMENSIONS`.
- **Railway-specific files** (`railway.json`) are harmless on Render (ignored) — kept for
  reference; remove if you prefer.
