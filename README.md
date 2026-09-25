# Precision AI

**AI-powered IT helpdesk: ticketing, troubleshooting and autonomous resolution.**

Employees describe a problem to a chatbot instead of emailing IT. Precision AI understands it, asks only the questions it needs, generates a validated ticket, checks for duplicates and company-wide incidents, tries **verified** fixes first, uses an LLM only when that is actually needed, asks the employee to confirm, and escalates to the right team with a complete hand-off package when it cannot solve the issue safely. Every confirmed or IT-approved fix becomes reusable knowledge.

| | |
|---|---|
| Backend | Python 3.12 · FastAPI · SQLAlchemy 2 (async) · Alembic · pydantic |
| Database | **PostgreSQL** (source of truth; SQLite supported for zero-setup local runs) |
| Vector search | **FAISS** (exact cosine, keyed by PostgreSQL ids, auto-rebuilt) · sentence-transformers `all-MiniLM-L6-v2` |
| LLMs (optional) | provider-agnostic: Ollama (local), Groq, OpenAI, Gemini — small/large tiers with fallback |
| Frontend | React 19 · TypeScript · Vite · Tailwind CSS v4 · Recharts |
| Ops | multi-stage Docker image · docker-compose (PostgreSQL + optional Ollama) · GitHub Actions CI |

## What it does

* **Conversational intake** — at most two targeted follow-ups (symptom, scope) with one-tap quick replies; screenshots/logs can be attached.
* **Ticket intelligence** — category, sub-category, intent, entities, confidence. LLM output (when used) is schema-validated and restricted to active categories.
* **Priority validation** — impact × severity rules, plus a clamped LLM opinion when the rules are unsure. The employee's priority is never silently overridden: both are stored and an alert explains the difference.
* **Duplicate detection & incident correlation** — same-user repeats are linked instead of re-worked; three or more employees reporting the same thing within 60 minutes are grouped into an incident (e.g. `INCIDENT-EMAIL-001`), their troubleshooting stops, and resolving the incident closes every linked ticket.
* **Cost-optimised routing (L0–L5)** — deterministic policy → rules → similarity → verified-knowledge reuse (no LLM) → small/local model → large model only on retries or ambiguity. Every LLM call, token and cache hit is tracked.
* **RAG with provenance** — answers are labelled *VERIFIED*, *HUMAN-APPROVED*, *USER-CONFIRMED* or *AI-GENERATED*; generated steps must cite retrieved sources and pass a safety filter.
* **Troubleshooting agent** — persistent state machine (UNDERSTAND → … → VERIFY → RESOLVED / RETRY / ESCALATE). SAFE diagnostics run automatically, RESTRICTED actions need the employee's approval, DANGEROUS ones an admin's. There is no arbitrary-shell tool.
* **Escalation engine** — routes category → owning team, auto-assigns the least-loaded agent, attaches a package (attempts, diagnostics, retrieved knowledge, decision summary — never hidden reasoning).
* **IT support console** — queues, accept/assign, notes, steps, resolve-as-knowledge, correct category/priority, verify/reject AI knowledge, approvals.
* **Admin analytics** — computed from the database: tickets/day, AI resolution %, escalation %, duplicates prevented, resolution time, categories/intents/priorities, agent success rate, retrieval hit rate, KB growth, LLM usage and estimated token/cost savings; user & category management; index rebuild; audit log.

Details: [Architecture](docs/ARCHITECTURE.md) · [API](docs/API.md) · [Deployment](docs/DEPLOYMENT.md) · [Measured results](docs/EVALUATION.md)

## Quick start

### Option 1 — Docker (PostgreSQL)

```bash
cp .env.example .env          # set SECRET_KEY; optionally GROQ_API_KEY / OPENAI_API_KEY
docker compose up --build     # http://localhost:8000  (demo data is seeded on first start)
```

### Option 2 — local on Windows, no Docker (SQLite)

```powershell
.\run-local.ps1               # venv, migrations, seed, UI build, then http://localhost:8000
.\run-local.ps1 -Dev          # + Vite hot-reload dev server on http://localhost:5173
.\run-local.ps1 -Reset        # start again from a clean database
```

### Option 3 — manual (any OS)

```bash
cd backend
python -m venv venv && source venv/bin/activate          # Windows: venv\Scripts\activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-dev.txt
cp ../.env.example .env                                   # set DATABASE_URL (PostgreSQL, or sqlite+aiosqlite:///./precision_ai.db)
alembic upgrade head
python -m app.database.seed                               # synthetic demo data + live agent replay
uvicorn app.main:app --reload                             # API on :8000 (Swagger at /docs)

cd ../frontend && npm install && npm run dev              # UI on :5173 (proxies /api to :8000)
```

### Demo accounts (seed data — local use only)

| Role | Username | Password |
|---|---|---|
| Employee | `johndoe` (also `arivera`, `schen`, `ewhite`, …) | `Employee@123` |
| IT support | `itsupport` (Network), `iam.agent`, `mail.agent`, `hw.agent`, `sec.agent`, `dba.agent`, `ops.agent`, `app.agent`, `print.agent`, `desk.agent` | `Support@123` |
| Admin | `admin` | `Admin@123` |

All seed people, tickets and emails are synthetic (`@example.com`). For a real deployment use `SEED_DEMO_DATA=false` and the bootstrap admin variables ([deployment guide](docs/DEPLOYMENT.md)).

### Enabling LLMs (optional)

Without any model the system runs levels 0–3 deterministically and escalates what it cannot solve. To enable levels 4–5:

* **Local, free:** install [Ollama](https://ollama.com) and `ollama pull llama3.2` (the default small tier).
* **Cloud:** set `GROQ_API_KEY` ([get one](https://console.groq.com/keys)) for the default large tier, `openai/gpt-oss-120b`. To use another provider, set `LLM_LARGE_PROVIDER=openai|gemini` and its key; the tier then uses that provider's default model (`OPENAI_MODEL`, `GEMINI_MODEL`) unless `LLM_LARGE_MODEL` is set.

If only one tier is reachable, the other tier's tasks fall back to it. `/admin` → *System status* shows which tiers are configured. A failed call logs the provider's reason (e.g. `llm_call ok=False error='groq: HTTP 401 - Invalid API Key'`) in the server console and in `GET /api/v1/admin/llm-calls`.

## Tests & evaluation

```bash
cd backend
pytest -q                                                            # 79 tests on SQLite
TEST_DATABASE_URL=postgresql+asyncpg://user:pass@host/db pytest -q   # same suite on PostgreSQL
python -m app.scripts.evaluate                                       # held-out accuracy / duplicate P-R
cd ../frontend && npm run typecheck && npm run build
```

Latest run: **79/79 tests pass on SQLite and on PostgreSQL 16**. On the held-out set, the rules-only classifier reaches 87.5% category accuracy, priority is within one level 97.5% of the time, and duplicate detection scores 0.82 precision / 0.90 recall ([details and known misses](docs/EVALUATION.md)).

## Repository layout

```
backend/
  app/
    agents/        state machine + troubleshooting agent
    api/v1/        routers: auth, chat, tickets, actions, incidents, knowledge, support, admin, meta
    core/          settings, JWT/bcrypt security, RBAC dependencies, structured logging
    database/      async engine/session, seed data
    embeddings/    sentence-transformers (+ hashing fallback)
    llm/           provider abstraction + tiered router (cache, validation, usage log)
    models/        SQLAlchemy models
    rag/           retriever (FAISS → PostgreSQL + validation) and grounded generator
    services/      chat, classification, priority, correlation, escalation, knowledge, tickets, analytics
    tools/         tool registry (permissions), executor (approvals), safety filter
    vector_store/  VectorStore interface, FAISS implementation, index manager
    scripts/       evaluate, bootstrap
  migrations/      Alembic
  tests/           pytest suite
frontend/src/      React app (pages, components, services, context, hooks)
data/              knowledge-base runbooks, service catalog, seed + evaluation sets
docs/              architecture, API (+ openapi.json), deployment, evaluation, resume
docker/  Dockerfile  docker-compose.yml  .env.example  run-local.ps1  .github/workflows/ci.yml
```

## Security notes

Passwords are bcrypt-hashed; JWT access tokens are short-lived with refresh tokens; roles are enforced server-side on every endpoint; employees can only read their own tickets and attachments; logs redact secret-like fields; uploads are type- and size-limited and stored under random names; `.env` is git-ignored. Restricted device/identity actions are recorded in dry-run mode until a real connector is configured — see the limitations section of the architecture doc.
