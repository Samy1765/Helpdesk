# Precision AI — resume description

**Precision AI — AI-Powered IT Helpdesk & Autonomous Resolution System** (Python, FastAPI, PostgreSQL, FAISS, React/TypeScript, Docker)

- Built an end-to-end IT helpdesk where employees report issues to a chatbot that asks targeted follow-ups, generates schema-validated tickets, and validates user-assigned priority with an impact × severity rules engine (97.5% within one level on a held-out labelled set).
- Designed a six-level cost-optimised routing pipeline (deterministic policy → rules → embedding similarity → verified-solution retrieval → small/local LLM → large LLM) with provider-agnostic LLM tiers, response caching and per-call token/cost tracking; the system resolves and escalates tickets with no LLM available.
- Implemented RAG and semantic duplicate detection over PostgreSQL + FAISS (MiniLM embeddings, category-gated thresholds calibrated on measured paraphrase similarity; 0.82 precision / 0.90 recall on held-out duplicate pairs), plus an incident-correlation engine that groups multi-user reports into one incident and closes all linked tickets on resolution.
- Engineered a persistent state-machine troubleshooting agent with permission-tiered tools (safe / restricted / dangerous) and human approval, a trust-ladder knowledge loop, and department escalation packages; verified by a 79-test pytest suite passing on SQLite and PostgreSQL 16, Alembic migrations and a Dockerised deployment.

*Every figure above is measured (see `docs/EVALUATION.md`). The evaluation set is small and author-written, so quote it as such if asked. No production usage metrics are claimed.*
