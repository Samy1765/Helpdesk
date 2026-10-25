# Precision AI

**AI-powered IT helpdesk: ticketing, troubleshooting and autonomous resolution.**

Employees describe a problem to a chatbot instead of emailing IT. Precision AI understands the problem, asks only the questions it needs, creates a validated ticket, checks for duplicates and company-wide incidents, tries **verified** fixes first, uses an LLM only when it is actually needed, asks the employee to confirm the fix, and escalates to the right team with a complete hand-off package when it cannot solve the issue safely. Every confirmed or IT-approved fix becomes reusable knowledge.

| | |
|---|---|
| Backend | Python 3.12 · FastAPI · SQLAlchemy 2 (async) · Alembic · pydantic |
| Database | **PostgreSQL** (source of truth; SQLite supported for zero-setup local runs) |
| Vector search | **FAISS** (exact cosine, keyed by database ids, auto-rebuilt) · sentence-transformers `all-MiniLM-L6-v2` |
| LLMs (optional) | Provider-agnostic: Ollama (local), Groq, OpenAI, Gemini, with small/large tiers and fallback |
| Frontend | React 19 · TypeScript · Vite · Tailwind CSS v4 · Recharts · self-hosted IBM Plex |
| Ops | Multi-stage Docker image · docker-compose (PostgreSQL + optional Ollama) · GitHub Actions CI |

## What it does

* **Conversational intake**: at most two targeted follow-up questions (symptom, scope) with one-tap replies. Screenshots and logs can be attached.
* **Ticket intelligence**: category, sub-category, intent, entities and confidence. LLM output (when used) is schema-validated and restricted to active categories.
* **Priority validation**: impact × severity rules, plus a clamped LLM opinion when the rules are unsure. The employee's priority is never silently overridden: both values are stored and the difference is explained.
* **Duplicate detection and incident correlation**: repeat reports from the same user are linked instead of re-worked. When three or more employees report the same thing within 60 minutes, their tickets are grouped into an incident (e.g. `INCIDENT-EMAIL-001`), troubleshooting stops, and resolving the incident closes every linked ticket.
* **Cost-optimised routing (levels L0 to L5)**: deterministic policy → rules → similarity → verified-knowledge reuse (no LLM) → small/local model → large model only on retries or ambiguity. Every LLM call, token and cache hit is tracked.
* **RAG with provenance**: answers are labelled *verified by IT*, *confirmed by employees* or *AI suggestion*. Generated steps must cite retrieved sources and pass a safety filter.
* **Troubleshooting agent**: a persistent state machine (UNDERSTAND → … → VERIFY → RESOLVED / RETRY / ESCALATE). SAFE diagnostics run automatically, RESTRICTED actions need the employee's approval, and DANGEROUS ones need an admin's. There is no arbitrary-shell tool.
* **Escalation engine**: routes each category to its owning team, auto-assigns the least-loaded engineer, and attaches a hand-off package (attempts, diagnostics, retrieved knowledge, decision summary).
* **IT support queue**: views, assign, notes, resolve-as-knowledge, correct category/priority, verify/decline fixes, approvals, SLA tracking.
* **Admin analytics** (computed from the database): tickets per day, share resolved by the agent, SLA compliance by priority, employee ratings, how tickets were handled (routing level), duplicates absorbed, knowledge-base growth, LLM usage and estimated savings, plus people, categories, search-index rebuild and an audit log.
* **Knowledge base**: 43 IT runbooks (Symptoms, Resolution, Escalation criteria, owner, last-reviewed date) and 33 human-verified fixes the agent reuses without a model call.
* **Security**: server-side sessions with refresh-token rotation and revocation, lockout and rate limits, strict CSP and security headers, content-checked uploads, a prompt-injection boundary around every LLM call, role checks tested on every privileged route. See the [security review](docs/SECURITY.md).

More details: [Architecture](docs/ARCHITECTURE.md) · [API](docs/API.md) · [Deployment](docs/DEPLOYMENT.md) · [Measured results](docs/EVALUATION.md) · [Security review](docs/SECURITY.md) · [Screenshots](docs/screenshots/README.md)

---

## How to run it

Pick **one** of the three options below. When it is running, open **http://localhost:8000** and sign in with one of the [demo accounts](#demo-accounts). The interactive API documentation (Swagger) is at **http://localhost:8000/docs** in development (it loads its scripts from a CDN, so it needs internet; the app itself does not).

### Option 1: Docker (recommended for the demo, any OS, uses PostgreSQL)

**You need:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/macOS) or Docker Engine + Compose (Linux).

```bash
cp .env.example .env          # Windows PowerShell: Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # paste the output into SECRET_KEY= in .env
docker compose up --build
```

The first build takes 10–20 minutes (it downloads Python, Node, PyTorch and the embedding model). On the first start the container creates the tables, loads the fictional demo company (`SEED_DEMO_DATA=true` in `.env.example`) and prints every demo account. After that the app runs **fully offline**: the embedding model and fonts are inside the image, and no LLM is needed.

* Stop: press `Ctrl+C`, or run `docker compose down`
* Start again later: `docker compose up` (seeding is idempotent; nothing is duplicated)
* Wipe all data and start fresh: `docker compose down -v`

### Option 2: Windows without Docker (one script, uses SQLite)

**You need:** [Python 3.12](https://www.python.org/downloads/) (tick *"Add Python to PATH"* in the installer) and [Node.js 22 LTS](https://nodejs.org/).

Open PowerShell in the project folder and run:

```powershell
.\run-local.ps1               # creates the venv, migrates, seeds the demo company, builds the UI, serves http://localhost:8000
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

Edit `backend/.env`: set `SECRET_KEY`, and add a database line at the end. For the simplest setup, use SQLite:

```
DATABASE_URL=sqlite+aiosqlite:///./precision_ai.db
```

(or `postgresql+asyncpg://user:password@localhost:5432/precision_ai` for PostgreSQL). Then:

```bash
alembic upgrade head                                       # create the database tables
python -m app.database.seed                                # demo company (SEED_DEMO_DATA=true) + knowledge base
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

### Demo accounts

All people, addresses and incidents belong to **Acme Demo Industries**, a fictional company (`@acme-demo.in`). For local demos only; a real deployment uses `SEED_DEMO_DATA=false` and the bootstrap admin variables (see the [deployment guide](docs/DEPLOYMENT.md)).

| Role | Accounts | Password |
|---|---|---|
| Administrator | `admin` (Morgan Admin), `it.manager` (Nisha Raghavan) | `Admin@123` |
| IT support (11) | `itsupport` (Network Team), `iam.agent`, `mail.agent`, `hw.agent`, `sec.agent`, `dba.agent`, `ops.agent`, `app.agent`, `print.agent`, `desk.agent`, `desk2.agent` | `Support@123` |
| Employees (60, 15 departments) | `johndoe` (Engineering), `priyanka.das` (Customer Support), `manoj.patil` (Manufacturing), `sneha.kapoor` (Marketing), `ewhite` (Finance), … | `Employee@123` |

The seed prints the full list at the end, grouped by department. The demo quarter has about 360 tickets over the last 90 days (Monday peaks, office-hours arrivals), four resolved historical incidents (e-mail, VPN, printing, Bengaluru Wi-Fi), approvals, ratings and SLA outcomes, plus a live e-mail incident and a few tickets waiting for approval created on the day you seed.

### A five-minute demo

1. **Employee** (`johndoe`): *Home* shows the active e-mail incident and recent requests. Open **Get help**, type *"GlobalProtect keeps dropping every few minutes while I'm on Teams calls"*, and answer *Connects then drops out* and *Just me*. The agent proposes a fix **verified by IT** with no AI model involved (routing level L3), and asks you to approve *Restart VPN client service*. Approve, click **Yes, it's fixed**, then rate the ticket on its page.
2. **IT support** (`itsupport`): **Support queue** shows open work, tickets past SLA and approvals waiting. Open an escalated ticket, add an internal note, resolve it with *Save as verified knowledge* ticked.
3. **Administrator** (`admin`): **Analytics and administration** for the last 90 days (SLA by priority, ratings, how tickets were handled, knowledge growth) and the audit log (sign-ins, failed sign-ins, role changes, approvals).
4. **Security**: sign in as `ghost.user` (an account that does not exist) with any password six times. The answers are exactly what a real account would get (*Invalid username or password*, then *Too many failed sign-in attempts. Try again in 15 min.*), so the screen never reveals which usernames exist. Don't do this with an account you still need in the demo. The failed attempts appear in the admin audit log, and `curl -I http://localhost:8000/login` shows the CSP and other security headers.

### Enabling LLMs (optional)

Without any model, the system runs levels 0 to 3 deterministically and escalates what it cannot solve. To enable levels 4 and 5:

* **Local and free:** install [Ollama](https://ollama.com) and run `ollama pull llama3.2` (the default small tier). With Docker, use `docker compose --profile llm up --build`, then `docker compose exec ollama ollama pull llama3.2`.
* **Cloud:** set `GROQ_API_KEY` ([get one](https://console.groq.com/keys)) for the default large tier, `openai/gpt-oss-120b`. To use another provider instead, set `LLM_LARGE_PROVIDER=openai` or `gemini` together with that provider's key; the tier then uses that provider's own default model (`OPENAI_MODEL`, `GEMINI_MODEL`) unless `LLM_LARGE_MODEL` is set explicitly. A cloud tier needs internet during the demo.

If only one tier is reachable, the other tier's tasks fall back to it. The *System status* panel on the admin page shows which tiers are reachable.

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

* Allow roughly **5 GB of free disk space** and a stable internet connection for the **first build** (PyTorch and the embedding model are large downloads). Build the day before the demo; after that no internet is needed.
* If port 8000 is already in use, set `APP_PORT=8080` in `.env` for Docker, or run `uvicorn app.main:app --port 8080` manually, and open `http://localhost:8080`.
* **Showing it to people on the same Wi-Fi without installing anything on their laptops:** run it on your own laptop, find your IP address (`ipconfig` on Windows, `ip addr` / `ifconfig` on Linux/macOS), and have them open `http://<your-ip>:8000`. Docker already listens on all network interfaces. With the manual setup, start the server with `uvicorn app.main:app --host 0.0.0.0 --port 8000`. (`run-local.ps1` only listens on `127.0.0.1`.) You may need to allow port 8000 through your firewall.

---

## Tests and evaluation

```bash
cd backend
pytest -q                                                            # 242 tests on SQLite
TEST_DATABASE_URL=postgresql+asyncpg://user:pass@host/db pytest -q   # same suite on PostgreSQL
python -m app.scripts.evaluate                                       # held-out accuracy / duplicate precision-recall
cd ../frontend && npm run typecheck && npm run lint:design && npm run build
```

Latest run: **242/242 tests pass**. On the held-out set, the rules-only classifier reaches 87.5% category accuracy, priority is within one level 97.5% of the time, and duplicate detection scores 0.82 precision / 0.90 recall ([details and known misses](docs/EVALUATION.md)). These numbers did not change in this release: classification and priority rules were not modified, and a test checks that the evaluation set's text appears nowhere in the seed data, knowledge base or tests.

`npm run lint:design` keeps the interface on its design system (type scale, spacing, no gradients or emoji); `pip-audit` and `npm audit` report no known vulnerabilities.

## Repository layout

```
backend/
  app/
    agents/        state machine + troubleshooting agent
    api/v1/        routers: auth, chat, tickets, actions, incidents, knowledge, support, admin, meta
    core/          settings, JWT/bcrypt security, RBAC, middleware (headers, body limits), rate limiting, logging
    database/      async engine/session, reference + knowledge seed, demo company (demo.py)
    embeddings/    sentence-transformers (+ hashing fallback)
    llm/           provider abstraction, tiered router, prompt-injection boundary (untrusted.py)
    models/        SQLAlchemy models
    rag/           retriever (FAISS -> database + validation) and grounded generator
    services/      chat, classification, priority, correlation, escalation, knowledge, tickets, analytics, auth, uploads
    tools/         tool registry (permissions), executor (approvals), safety filter
    vector_store/  VectorStore interface, FAISS implementation, index manager
    scripts/       evaluate, bootstrap
  migrations/      Alembic (0001 schema, 0002 sessions, 0003 knowledge review dates)
  tests/           pytest suite
frontend/src/      React app (pages, components, lib/format, services, context, hooks)
frontend/scripts/  design guard (check-design.mjs)
data/              43 runbooks, verified solutions, service catalog, seed + evaluation sets
docs/              architecture, API (+ openapi.json), deployment, evaluation, security review, screenshots, resume
docker/  Dockerfile  docker-compose.yml  .env.example  run-local.ps1  .github/workflows/ci.yml
```

## Security notes

* Passwords are hashed with bcrypt; sign-in is throttled per account and per client IP, and errors never reveal whether an account exists.
* Every sign-in is a server-side session: access tokens are short-lived, refresh tokens rotate on each use, and logout, password changes and deactivation revoke sessions immediately.
* Roles are enforced server-side on every endpoint (and tested route by route); employees can only read their own tickets and attachments.
* Strict CSP, `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, HSTS behind HTTPS, request-size limits.
* Uploads are checked by extension *and* content, stored under random names, and always served as downloads.
* Text sent to an LLM is fenced as untrusted data; model output is schema-validated, safety-filtered and never executed.
* The app refuses to start outside development with a placeholder `SECRET_KEY`; `.env` is git-ignored and `.env.example` documents every setting.
* Restricted device and identity actions are only recorded (dry-run mode) until a real connector is configured.

The full review, with file and line references, risks, fixes and accepted residual risks, is in [docs/SECURITY.md](docs/SECURITY.md).
