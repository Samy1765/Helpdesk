# Deployment

## Option A — Docker Compose (single host)

```bash
cp .env.example .env
# edit .env: set SECRET_KEY, APP_ENV=production, strong POSTGRES_PASSWORD,
# SEED_DEMO_DATA=false for a real deployment, optional GROQ_API_KEY / OPENAI_API_KEY
docker compose up -d --build
# optional local model server:
docker compose --profile llm up -d && docker compose exec ollama ollama pull llama3.2
```

The app container runs `alembic upgrade head` on every start (idempotent), then either seeds the demo company (`SEED_DEMO_DATA=true`, idempotent) or runs the production bootstrap, then serves API + SPA on port 8000 with one worker. Volumes: `pgdata` (PostgreSQL), `faiss` (indexes — rebuilt automatically from PostgreSQL if lost), `uploads`.

The image is self-contained at run time: the embedding model is baked in and `HF_HUB_OFFLINE=1` stops any Hub lookups, the fonts are bundled with the frontend, and with no LLM configured nothing calls out to the internet. Only `/docs` (Swagger UI loads from a CDN) and the optional cloud LLM tiers need a network.

## Option B — Cloud (container platform + managed PostgreSQL)

Works on AWS ECS/Fargate, Azure Container Apps, Google Cloud Run (min instances = 1), Render, Fly.io:

1. Provision managed PostgreSQL 14+ and set `DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db`.
2. Build and push the image: `docker build -t <registry>/precision-ai:1.0 . && docker push ...`.
3. Run **one** instance (FAISS is in-process; see scaling) with env vars from `.env.example` (`APP_ENV=production`, `SECRET_KEY` from the platform's secret store, LLM keys as secrets, `LOG_FORMAT=json`).
4. Mount persistent storage at `/app/faiss_indexes` and `/app/data/uploads` (or accept index rebuilds on restart; uploads need durable storage — an object-store connector is the natural next step).
5. Health check: `GET /health`. Put TLS termination in front and set `FORWARDED_ALLOW_IPS` to the proxy's address so `X-Forwarded-For` / `X-Forwarded-Proto` are trusted from it alone (the default trusts only `127.0.0.1`). HSTS is sent once requests arrive over HTTPS.
6. Set `CORS_ORIGINS` only if the SPA is served from a different origin (by default FastAPI serves it same-origin).

## Production checklist

- [ ] `APP_ENV=production`. Outside `development`/`test` the app refuses to start with a placeholder or short (< 32 characters) `SECRET_KEY` or a wildcard `CORS_ORIGINS`
- [ ] Unique `SECRET_KEY`, database password and LLM keys stored as secrets — never in git
- [ ] `FORWARDED_ALLOW_IPS` set to the reverse proxy; TLS terminated in front of the app
- [ ] `ALLOW_SELF_REGISTRATION=false` if accounts come from IT; review `LOGIN_MAX_FAILURES`, `LOGIN_LOCKOUT_MINUTES` and the `RATE_LIMIT_*` values
- [ ] Swagger / ReDoc / OpenAPI are off in production unless `API_DOCS_ENABLED=true`
- [ ] Keep `AGENT_TOOLS_ENABLED=false` until `data/service_catalog.json` lists your own internal endpoints
- [ ] `SEED_DEMO_DATA=false` plus `BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD` — the container then runs `python -m app.scripts.bootstrap` (roles, teams, categories, IT knowledge base, first admin; no demo users or tickets)
- [ ] Replace example hosts in `data/service_catalog.json` with real endpoints (VPN gateway, mail, DB listeners)
- [ ] Replace the sample runbooks in `data/knowledge` (written for the fictional Acme Demo Industries) with your own, keeping the Symptoms / Resolution / Escalation criteria structure
- [ ] Wire a real `ActionConnector` (endpoint management / identity) if restricted actions should execute rather than be recorded
- [ ] Back up PostgreSQL; FAISS needs no backup (rebuildable)
- [ ] Ship JSON logs to your log platform; alert on `unhandled_error`, `llm_call ok=false`, `ticket_escalated` spikes

## Scaling

* Vertical scaling is straightforward (async I/O, embedding inference runs in a thread).
* For multiple API replicas, replace FAISS with **pgvector** by implementing `app/vector_store/base.py:VectorStore` — every other component already treats the vector store as a replaceable index over PostgreSQL ids.
* LLM calls are the slowest step; they are bounded by `LLM_TIMEOUT_SECONDS` / `LLM_MAX_RETRIES` and only happen at routing levels 4–5.

## Local development without Docker

See the README. SQLite is supported for zero-setup local runs; PostgreSQL is used by Docker, CI and production. The test suite runs on both (`TEST_DATABASE_URL=postgresql+asyncpg://... pytest`).
