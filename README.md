# Precision AI

**AI-powered IT helpdesk: ticketing, troubleshooting and autonomous resolution.**

Employees describe a problem to a chatbot instead of emailing IT. Precision AI understands it, asks only the questions it needs, generates a validated ticket, checks for duplicates and company-wide incidents, tries **verified** fixes first, uses an LLM only when that is actually needed, asks the employee to confirm, and escalates to the right team with a complete hand-off package when it cannot solve the issue safely. Every confirmed or IT-approved fix becomes reusable knowledge.

| | |
|---|---|
| Backend | Python 3.12 Â· FastAPI Â· SQLAlchemy 2 (async) Â· Alembic Â· pydantic |
| Database | **PostgreSQL** (source of truth; SQLite supported for zero-setup local runs) |
| Vector search | **FAISS** (exact cosine, keyed by PostgreSQL ids, auto-rebuilt) Â· sentence-transformers `all-MiniLM-L6-v2` |
| LLMs (optional) | provider-agnostic: Ollama (local), Groq, OpenAI, Gemini â€” small/large tiers with fallback |
| Frontend | React 19 Â· TypeScript Â· Vite Â· Tailwind CSS v4 Â· Recharts |
| Ops | multi-stage Docker image Â· docker-compose (PostgreSQL + optional Ollama) Â· GitHub Actions CI |

## What it does

* **Conversational intake** â€” at most two targeted follow-ups (symptom, scope) with one-tap quick replies; screenshots/logs can be attached.
* **Ticket intelligence** â€” category, sub-category, intent, entities, confidence. LLM output (when used) is schema-validated and restricted to active categories.
* **Priority validation** â€” impact Ã— severity rules, plus a clamped LLM opinion when the rules are unsure. The employee's priority is never silently overridden: both are stored and an alert explains the difference.
* **Duplicate detection & incident correlation** â€” same-user repeats are linked instead of re-worked; three or more employees reporting the same thing within 60 minutes are grouped into an incident (e.g. `INCIDENT-EMAIL-001`), their troubleshooting stops, and resolving the incident closes every linked ticket.
* **Cost-optimised routing (L0â€“L5)** â€” deterministic policy â†’ rules â†’ similarity â†’ verified-knowledge reuse (no LLM) â†’ small/local model â†’ large model only on retries or ambiguity. Every LLM call, token and cache hit is tracked.
* **RAG with provenance** â€” answers are labelled *VERIFIED*, *HUMAN-APPROVED*, *USER-CONFIRMED* or *AI-GENERATED*; generated steps must cite retrieved sources and pass a safety filter.
* **Troubleshooting agent** â€” persistent state machine (UNDERSTAND â†’ â€¦ â†’ VERIFY â†’ RESOLVED / RETRY / ESCALATE). SAFE diagnostics run automatically, RESTRICTED actions need the employee's approval, DANGEROUS ones an admin's. There is no arbitrary-shell tool.
* **Escalation engine** â€” routes category â†’ owning team, auto-assigns the least-loaded agent, attaches a package (attempts, diagnostics, retrieved knowledge, decision summary â€” never hidden reasoning).
* **IT support console** â€” queues, accept/assign, notes, steps, resolve-as-knowledge, correct category/priority, verify/reject AI knowledge, approvals.
* **Admin analytics** â€” computed from the database: tickets/day, AI resolution %, escalation %, duplicates prevented, resolution time, categories/intents/priorities, agent success rate, retrieval hit rate, KB growth, LLM usage and estimated token/cost savings; user & category management; index rebuild; audit log.

Details: [Architecture](docs/ARCHITECTURE.md) Â· [API](docs/API.md) Â· [Deployment](docs/DEPLOYMENT.md) Â· [Measured results](docs/EVALUATION.md)

## Quick start

### Option 1 â€” Docker (PostgreSQL)

```bash
cp .env.example .env          # set SECRET_KEY; optionally GROQ_API_KEY / OPENAI_API_KEY
docker compose up --build     # http://localhost:8000  (demo data is seeded on first start)
```

### Option 2 â€” local on Windows, no Docker (SQLite)

```powershell
.\run-local.ps1               # venv, migrations, seed, UI build, then http://localhost:8000
.\run-local.ps1 -Dev          # + Vite hot-reload dev server on http://localhost:5173
.\run-local.ps1 -Reset        # start again from a clean database
```

### Option 3 â€” manual (any OS)

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

### Demo accounts (seed data â€” local use only)

| Role | Username | Password |
|---|---|---|
| Employee | `johndoe` (also `arivera`, `schen`, `ewhite`, â€¦) | `Employee@123` |
| IT support | `itsupport` (Network), `iam.agent`, `mail.agent`, `hw.agent`, `sec.agent`, `dba.agent`, `ops.agent`, `app.agent`, `print.agent`, `desk.agent` | `Support@123` |
| Admin | `admin` | `Admin@123` |

All seed people, tickets and emails are synthetic (`@example.com`). For a real deployment use `SEED_DEMO_DATA=false` and the bootstrap admin variables ([deployment guide](docs/DEPLOYMENT.md)).

### Enabling LLMs (optional)

Without any model the system runs levels 0â€“3 deterministically and escalates what it cannot solve. To enable levels 4â€“5:

* **Local, free:** install [Ollama](https://ollama.com) and `ollama pull llama3.2` (the default small tier).
* **Cloud:** set `GROQ_API_KEY` (default large tier), or `LLM_LARGE_PROVIDER=openai|gemini` with its key.

`/admin` â†’ *System status* shows which tiers are reachable.

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
    rag/           retriever (FAISS â†’ PostgreSQL + validation) and grounded generator
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

Passwords are bcrypt-hashed; JWT access tokens are short-lived with refresh tokens; roles are enforced server-side on every endpoint; employees can only read their own tickets and attachments; logs redact secret-like fields; uploads are type- and size-limited and stored under random names; `.env` is git-ignored. Restricted device/identity actions are recorded in dry-run mode until a real connector is configured â€” see the limitations section of the architecture doc.
