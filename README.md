# Precision AI

**AI-powered IT helpdesk: ticketing, troubleshooting and autonomous resolution.**

Employees describe a problem to a chatbot instead of emailing IT. Precision AI understands the problem, asks only the questions it needs, creates a validated ticket, checks for duplicates and company-wide incidents, tries **verified** fixes first, uses an LLM only when it is actually needed, asks the employee to confirm the fix, and escalates to the right team with a complete hand-off package when it cannot solve the issue safely. Every confirmed or IT-approved fix becomes reusable knowledge.

| | |
|---|---|
| Backend | Python 3.12 · FastAPI · SQLAlchemy 2 (async) · Alembic · pydantic |
| Database | **PostgreSQL** (source of truth; SQLite supported for zero-setup local runs) |
| Vector search | **FAISS** (exact cosine, keyed by database ids, auto-rebuilt) · sentence-transformers `all-MiniLM-L6-v2` |
| LLMs (optional) | Provider-agnostic: Ollama (local), Groq, OpenAI, Gemini, with small/large tiers and fallback |
| Frontend | React 19 · TypeScript · Vite · Tailwind CSS v4 · Recharts |
| Ops | Multi-stage Docker image · docker-compose (PostgreSQL + optional Ollama) · GitHub Actions CI |

## What it does

* **Conversational intake**: at most two targeted follow-up questions (symptom, scope) with one-tap quick replies. Screenshots and logs can be attached.
* **Ticket intelligence**: category, sub-category, intent, entities and confidence. LLM output (when used) is schema-validated and restricted to active categories.
* **Priority validation**: impact × severity rules, plus a clamped LLM opinion when the rules are unsure. The employee's priority is never silently overridden: both values are stored and an alert explains the difference.
* **Duplicate detection and incident correlation**: repeat reports from the same user are linked instead of re-worked. When three or more employees report the same thing within 60 minutes, their tickets are grouped into an incident (e.g. `INCIDENT-EMAIL-001`), troubleshooting stops, and resolving the incident closes every linked ticket.
* **Cost-optimised routing (levels L0 to L5)**: deterministic policy → rules → similarity → verified-knowledge reuse (no LLM) → small/local model → large model only on retries or ambiguity. Every LLM call, token and cache hit is tracked.
* **RAG with provenance**: answers are labelled *VERIFIED*, *HUMAN-APPROVED*, *USER-CONFIRMED* or *AI-GENERATED*. Generated steps must cite retrieved sources and pass a safety filter.
* **Troubleshooting agent**: a persistent state machine (UNDERSTAND → … → VERIFY → RESOLVED / RETRY / ESCALATE). SAFE diagnostics run automatically, RESTRICTED actions need the employee's approval, and DANGEROUS ones need an admin's. There is no arbitrary-shell tool.
* **Escalation engine**: routes each category to its owning team, auto-assigns the least-loaded agent, and attaches a package (attempts, diagnostics, retrieved knowledge, decision summary; never hidden reasoning).
* **IT support console**: queues, accept/assign, notes, steps, resolve-as-knowledge, correct category/priority, verify/reject AI knowledge, approvals.
* **Admin analytics** (computed from the database): tickets per day, AI resolution %, escalation %, duplicates prevented, resolution time, categories/intents/priorities, agent success rate, retrieval hit rate, knowledge-base growth, LLM usage and estimated token/cost savings. Also user and category management, index rebuild and an audit log.

More details: [Architecture](docs/ARCHITECTURE.md) · [API](docs/API.md) · [Deployment](docs/DEPLOYMENT.md) · [Measured results](docs/EVALUATION.md)

---

## How to run it

Pick **one** of the three options below. When it is running, open **http://localhost:8000** in a browser and log in with one of the [demo accounts](#demo-accounts-seed-data--local-use-only). The interactive API documentation (Swagger) is at **http://localhost:8000/docs**.

### Option 1: Docker (easiest, any OS, uses PostgreSQL)

**You need:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/macOS) or Docker Engine + Compose (Linux).

```bash
cp .env.example .env          # Windows PowerShell: Copy-Item .env.example .env
# Open .env and set SECRET_KEY to a long random string (optional: GROQ_API_KEY / OPENAI_API_KEY)
docker compose up --build
```

The first build takes several minutes (it downloads Python, Node, PyTorch and the embedding model). Demo data is loaded automatically on the first start.

* Stop: press `Ctrl+C`, or run `docker compose down`
* Start again later: `docker compose up`
* Wipe all data and start fresh: `docker compose down -v`

### Option 2: Windows without Docker (one script, uses SQLite)

**You need:** [Python 3.12](https://www.python.org/downloads/) (tick *"Add Python to PATH"* in the installer) and [Node.js 22 LTS](https://nodejs.org/).

Open PowerShell in the project folder and run:

```powershell
.\run-local.ps1               # creates the venv, migrates, seeds, builds the UI, then serves http://localhost:8000
.\run-local.ps1 -Dev          # also starts the Vite hot-reload dev server on http://localhost:5173
.\run-local.ps1 -Reset        # start again from a clean database
```

If PowerShell says *"running scripts is disabled on this system"*, run this once in the same window and try again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

The first run takes several minutes because it installs all Python and Node packages.

### Option 3: Manual setup (any OS)

**You need:** Python 3.11+ (3.12 recommended), Node.js 22, and optionally PostgreSQL (otherwise SQLite is used).

**1. Backend** (terminal 1):

```bash
cd backend
python -m venv venv
source venv/bin/activate                                   # Windows: venv\Scripts\activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-dev.txt
cp ../.env.example .env                                    # Windows: copy ..\.env.example .env
```

Edit `backend/.env` and add a database line at the end. For the simplest setup, use SQLite:

```
DATABASE_URL=sqlite+aiosqlite:///./precision_ai.db
```

(or `postgresql+asyncpg://user:password@localhost:5432/precision_ai` for PostgreSQL). Then:

```bash
alembic upgrade head                                       # create the database tables
python -m app.database.seed                                # load synthetic demo data (first time only)
uvicorn app.main:app --reload                              # API on http://localhost:8000
```

**2. Frontend** (terminal 2), choose one:

```bash
cd frontend
npm install
npm run dev        # development UI with hot reload on http://localhost:5173 (talks to the API on :8000)
# or
npm run build      # build once; the backend then serves the UI at http://localhost:8000
```

### Demo accounts (seed data, local use only)

| Role | Username | Password |
|---|---|---|
| Employee | `johndoe` (also `arivera`, `schen`, `ewhite`, …) | `Employee@123` |
| IT support | `itsupport` (Network), `iam.agent`, `mail.agent`, `hw.agent`, `sec.agent`, `dba.agent`, `ops.agent`, `app.agent`, `print.agent`, `desk.agent` | `Support@123` |
| Admin | `admin` | `Admin@123` |

All seed people, tickets and emails are synthetic (`@example.com`). For a real deployment use `SEED_DEMO_DATA=false` and the bootstrap admin variables (see the [deployment guide](docs/DEPLOYMENT.md)).

### Enabling LLMs (optional)

Without any model, the system runs levels 0 to 3 deterministically and escalates what it cannot solve. To enable levels 4 and 5:

* **Local and free:** install [Ollama](https://ollama.com) and run `ollama pull llama3.2` (the default small tier). With Docker, use `docker compose --profile llm up --build`, then `docker compose exec ollama ollama pull llama3.2`.
* **Cloud:** set `GROQ_API_KEY` in `.env` (the default large tier), or set `LLM_LARGE_PROVIDER=openai` or `gemini` together with that provider's key.

The *System status* panel on the `/admin` page shows which tiers are reachable.

---

## Running it on someone else's laptop

The code lives on GitHub, so the other person does **not** need a copy of your folder. Secrets and generated files (`.env`, `venv/`, `node_modules/`, the database) are git-ignored and are recreated on their machine.

**Step 1: Get the code onto their laptop.**

* If the repository is **private**, first add them as a collaborator: GitHub → *Settings* → *Collaborators* → *Add people*.
* Then, on their laptop, either install [Git](https://git-scm.com/downloads) and run:

  ```bash
  git clone https://github.com/Samy1765/Helpdesk.git
  cd Helpdesk
  ```

  or open the repository page on GitHub → green **Code** button → **Download ZIP**, and extract it.

**Step 2: Install the prerequisites for one option.**

| If they choose | They need to install |
|---|---|
| Option 1 (recommended) | Docker Desktop only; Python and Node are not needed |
| Option 2 (Windows) | Python 3.12 + Node.js 22 |
| Option 3 (manual) | Python 3.12 + Node.js 22 (+ PostgreSQL if not using SQLite) |

**Step 3: Follow the same steps** from [How to run it](#how-to-run-it) above, inside the project folder.

**Step 4: Create their own `.env`** from `.env.example`, with their own `SECRET_KEY` and (optionally) their own LLM API keys. Never send your `.env` file or API keys to anyone.

**Tips:**

* Allow roughly **5 GB of free disk space** and a stable internet connection for the first run (PyTorch and the embedding model are large downloads).
* If port 8000 is already in use, set `APP_PORT=8080` in `.env` for Docker, or run `uvicorn app.main:app --port 8080` manually, and open `http://localhost:8080`.
* **Showing it to people on the same Wi-Fi without installing anything on their laptops:** run it on your own laptop, find your IP address (`ipconfig` on Windows, `ip addr` / `ifconfig` on Linux/macOS), and have them open `http://<your-ip>:8000`. Docker already listens on all network interfaces. With the manual setup, start the server with `uvicorn app.main:app --host 0.0.0.0 --port 8000`. (`run-local.ps1` only listens on `127.0.0.1`.) You may need to allow port 8000 through your firewall.

---

## Tests and evaluation

```bash
cd backend
pytest -q                                                            # 79 tests on SQLite
TEST_DATABASE_URL=postgresql+asyncpg://user:pass@host/db pytest -q   # same suite on PostgreSQL
python -m app.scripts.evaluate                                       # held-out accuracy / duplicate precision-recall
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
    rag/           retriever (FAISS -> database + validation) and grounded generator
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

* Passwords are hashed with bcrypt.
* JWT access tokens are short-lived and paired with refresh tokens.
* Roles are enforced server-side on every endpoint, and employees can only read their own tickets and attachments.
* Logs redact secret-like fields.
* Uploads are limited by type and size, and stored under random names.
* `.env` is git-ignored.
* Restricted device and identity actions are only recorded (dry-run mode) until a real connector is configured. See the limitations section of the [architecture doc](docs/ARCHITECTURE.md).
