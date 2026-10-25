# Evaluation

Reproduce with:

```bash
cd backend
python -m app.scripts.evaluate
```

The script runs the **deterministic floor** of the system (no LLM) over `data/eval/eval_set.json`: 40 hand-labelled issue reports across all 10 categories and 20 labelled duplicate / non-duplicate pairs. The set is not used by the tests or the seed data (`tests/test_knowledge_base.py` fails if any 8-word sequence from it appears in the seed data, the knowledge base or the tests), but it was written by the project author, so treat it as a sanity check on realistic phrasing — not an independent benchmark.

## Results (all-MiniLM-L6-v2, measured 2026-09-25, re-run 2026-10-25 with identical results)

| Metric | Result |
|---|---|
| Category accuracy (rules only) | **87.5%** (35 / 40) |
| Priority — exact level | **72.5%** |
| Priority — within one level | **97.5%** |
| Duplicate detection precision (sim ≥ 0.55 + category gate) | **0.82** (9 TP, 2 FP) |
| Duplicate detection recall | **0.90** (1 FN) |

### Known misses (left un-tuned on purpose, to keep the set held-out)

| Text | Expected | Rules said |
|---|---|---|
| "cannot reach the company network from the hotel, globalprotect spins forever" | VPN | Network |
| "scanner won't send scans to my email" | Printer | Email |
| "could you install Tableau on my laptop please" | Software | Hardware |
| "all my files were renamed with a .locked extension and there's a ransom note" | Security | Software |
| "got an alert about a sign-in from another country that wasn't me" | Security | Software |

With an LLM configured, reports whose rule confidence is below 0.6 are re-classified by the small model (schema-validated, restricted to active categories), and IT can correct any ticket's category and priority from the ticket page.

## Pipeline behaviour on the seeded replay

`python -m app.database.seed` replays 11 employee reports through the real chat + agent pipeline (no LLM configured). Observed on both SQLite and PostgreSQL 16:

* 3 email-outage reports from different users → a new e-mail incident is created automatically (**INCIDENT-EMAIL-001**, or **INCIDENT-EMAIL-002** when the demo company's historical e-mail incident is present); earlier reports switched to "linked to incident".
* A repeated printer report from the same user → marked **duplicate** of the first.
* VPN MFA failure → **human-verified solution reused at L3 with zero LLM calls**, confirmed by the user → resolved; the solution's success counter incremented.
* Account lockout → restricted `unlock_account` action approved by the employee → resolved.
* Phishing with entered credentials, cracked screen → **L0 policy escalation** to Security / Hardware Support.
* Wi-Fi issue rejected twice → retry, then escalation to the Network Team with a full escalation package.

## Test suite

`pytest` — **242 tests**:

| File | Tests | Covers |
|---|---|---|
| `test_auth.py` | 8 | registration, login, roles, token types |
| `test_classification_priority.py` | 28 | classification of every category, priority rules |
| `test_agent_safety_llm.py` | 24 | state machine, tool permissions, safety filter, LLM router |
| `test_vector_rag.py` | 8 | FAISS persistence and drift rebuild, retrieval gating, trust ladder |
| `test_workflows.py` | 16 | end-to-end API: resolve, retry → escalate, duplicates, incidents, approvals, analytics, attachments |
| `test_security.py` | 69 | lockout and rate limits, session rotation and revocation, startup checks, headers, CORS, body limits, uploads, a 403 check on every IT/admin route, audit trail, prompt-injection boundary, safety filter cases, `.env.example` completeness (every setting documented and every shipped value loads), secret scan |
| `test_knowledge_base.py` | 83 | structure and review metadata of every runbook, every verified solution reusable without an LLM, procedure selection, FAISS rebuild, separation from the evaluation set |
| `test_demo_seed.py` | 6 | demo company seed end to end (migrations, counts, chronology, idempotency), ratings, SLA / satisfaction analytics |

The original 84 tests are unchanged and still pass. CI runs the suite on SQLite and on PostgreSQL 16.
