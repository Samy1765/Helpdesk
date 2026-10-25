# Security review

Scope: authentication, authorisation, input handling, file uploads, the chat → LLM path, configuration and
dependencies. File and line references point at commit `8126b23` (before the fixes). Every fix has a test in
`backend/tests/test_security.py` unless noted.

Severity: **H** = exploitable by a normal user or an unauthenticated client; **M** = needs a stolen token, a
known identifier or an unusual setup; **L** = hardening / defence in depth.

## Findings and fixes

### Authentication

| # | Where | Risk | Sev | Fix |
|---|---|---|---|---|
| 1 | `api/v1/endpoints/auth.py:100-107` | No rate limit or lockout: unlimited password guessing against any account, from any IP. | H | Per-identifier lockout (5 failures in 15 min → locked 15 min; applies to unknown usernames too, so a lockout reveals nothing) stored in `login_throttle`, plus a per-IP failed-login budget. Both answer `429` with `Retry-After`. |
| 2 | `auth.py:104` | bcrypt is skipped when the username does not exist, so response time reveals which usernames are real. | M | A dummy hash is verified for unknown users; the 401 message is identical in both cases. |
| 3 | `auth.py:149-155` | Refresh tokens are stateless: no rotation, still valid for 7 days after logout or a password change, impossible to revoke. | H | Server-side sessions (`auth_sessions`, migration `0002`). Every refresh rotates the token; replaying a rotated token revokes the session. Access tokens carry the session id and are rejected once it is revoked. A token replaced less than 30 s ago is still honoured once (two tabs refreshing at the same moment) and gets the current pair, not a new one; the SPA also shares one refresh between parallel requests. |
| 4 | `auth.py:158-162` | Logout only writes an audit row; both tokens keep working. | M | Logout revokes the session. |
| 5 | `auth.py:180-187` | Changing the password leaves every other session signed in; current-password guesses are unthrottled. | M | All sessions are revoked and a fresh one is issued; failed attempts are throttled. |
| 6 | `core/config.py:153-158` | The startup check only rejects keys starting with `dev-`; the `.env.example` placeholder passes, and non-`production` environments are never checked. | H | Any placeholder or key shorter than 32 characters stops start-up whenever `APP_ENV` is not `development`/`test`. |
| 7 | `auth.py:50,86` | bcrypt 5 raises on passwords over 72 bytes → HTTP 500 on register / change-password; login fields are unbounded. | L | Passwords limited to 72 UTF-8 bytes (422), login fields bounded. |

### Authorisation

| # | Where | Risk | Sev | Fix |
|---|---|---|---|---|
| 8 | `auth.py:170-177`, `auth.py:125` | `department_id` is not validated: an unknown id gives a 500, and an employee can move themselves into an IT team (shown to IT in escalation packages). | M | Self-service may only pick an existing business unit; team membership is admin-only. |
| 9 | `endpoints/chat.py:65-67` | The second attachment query is not filtered by owner: anyone holding another user's attachment token can attach it to their own ticket. | M | Only the caller's own attachments are linked. |
| 10 | `chat.py:115` | The requester cannot download a file IT attached to their ticket (functional authz bug). | L | The ticket's requester may download its attachments. |
| 11 | `endpoints/knowledge.py:59-72` | Semantic search returns other employees' original problem descriptions, entities and ticket ids to any employee. | M | Those fields are returned to IT staff only. |
| 12 | `agents/troubleshooting_agent.py:225-226` | The chat payload lists other employees' open tickets (number + title); the ticket page already restricts this. | L | Same rule as the ticket page: resolved tickets or the requester's own. |
| 13 | all routers | Nothing proves that every admin / IT route enforces its role. | M | A test walks every registered route and expects 403 for an employee (and for IT on admin routes). |
| 14 | `endpoints/admin.py:54-74` | Role changes and deactivations are logged as a generic `user_updated` without the old role; a deactivated user's sessions stay open; an unknown `department_id` gives a 500. | L | Dedicated `role_changed` (old → new), `user_deactivated` / `user_reactivated` and `user_department_changed` audit entries with the admin's IP; deactivation revokes sessions; departments are validated. Knowledge approvals (`solution_verified`, `solution_rejected`, `solution_created`) are audited too. |

### Input handling

| # | Where | Risk | Sev | Fix |
|---|---|---|---|---|
| 15 | `main.py` | No request-size limit: field limits apply only after the whole body has been read. | M | ASGI middleware (`core/middleware.py`): 1 MB for JSON, `MAX_UPLOAD_MB` + overhead for uploads. A declared `Content-Length` over the limit is refused before the body is read; a chunked body is cut off when it crosses the limit and the response is replaced by `413`. |
| 16 | `services/chat.py:228,245-247` | Clarifying answers are appended without a cap; long answers exceed the 8,000-character ticket limit → unhandled `ValidationError` → 500. | L | Description capped before validation. |
| 17 | `endpoints/chat.py:34,56` | `client_env` accepts any number of arbitrary keys; they are stored, shown to IT and fed to the LLM via diagnostics. | L | Allow-list of five keys, values truncated. |
| 18 | `main.py:68` | Client-supplied `X-Request-ID` is echoed into logs and responses unvalidated (log forging). | L | Accepted only if it matches `[A-Za-z0-9-]{1,64}`. |
| 19 | FastAPI default | 422 responses echo the submitted `input`, including password fields. | L | Custom handler returns `loc`, `msg`, `type` only. |

### File uploads

| # | Where | Risk | Sev | Fix |
|---|---|---|---|---|
| 20 | `chat.py:87-89` | The type check trusts the client's `Content-Type`; any bytes can be stored as `image/png`. No extension check, no content check, empty files accepted. | M | Extension allow-list plus magic-byte detection; the detected type must match the extension; text must be UTF-8/UTF-16 without NUL bytes. |
| 21 | `chat.py:96,101,117` | The original file name is stored as sent (path segments, control characters) and returned in `Content-Disposition`. | L | Name reduced to a safe base name; storage name stays random; paths are resolved inside `UPLOAD_DIR` on write and read. |

### Chat → LLM path

| # | Where | Risk | Sev | Fix |
|---|---|---|---|---|
| 22 | `services/classification.py:344`, `services/priority.py:174`, `rag/generator.py:111-136` | Employee text, ticket fields and diagnostics are concatenated into prompts with no boundary and no instruction to treat them as data (prompt injection). | M | `app/llm/untrusted.py`: employee text, ticket fields, diagnostics and retrieved knowledge go into `<untrusted name="…">` blocks; tag look-alikes and control characters inside them are removed, so a message cannot close its block. Every system prompt ends with the rule that block content is data. Model output stays schema-validated and is never executed: AI candidates cannot carry tool actions, even if the model returns some. |
| 23 | `tools/safety.py:9-26` | The output filter misses invented links and phone numbers, reworded credential requests, MFA removal, antivirus exclusions, download cradles (`certutil`, `bitsadmin`, `mshta`), shadow-copy deletion, log clearing, local-admin creation, execution-policy bypass, `netsh` firewall-off and world-writable ACLs. | M | Patterns added. Generated steps that contain a link or phone number which is not in the retrieved context are dropped (dates and short codes are not mistaken for phone numbers). Tests cover each new case, a set of normal instructions that must stay allowed, and every seeded KB procedure and solution, which must pass unchanged. |
| 24 | `endpoints/chat.py:54` | No limit on chat messages → unbounded paid-LLM spend if a cloud tier is configured. | L | Per-user limit on `/chat/message` and `POST /tickets` (`429`). |

### Configuration and deployment

| # | Where | Risk | Sev | Fix |
|---|---|---|---|---|
| 25 | `main.py:57-63`, `config.py:124` | CORS allows credentials, every method and header; default origins include an unused `:3000`. | M | Explicit origins only (wildcard refused outside development), no credentials (bearer tokens), explicit methods and headers. |
| 26 | `main.py` | No security headers. | M | CSP (strict for the app; relaxed only on `/docs` and `/redoc`), `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`; HSTS when the request arrived over HTTPS. |
| 27 | `docker/entrypoint.sh:25` | `--forwarded-allow-ips="*"` while port 8000 is published directly: any client can spoof its IP (audit log, per-IP limits). | M | `FORWARDED_ALLOW_IPS`, default `127.0.0.1`; set it to the reverse proxy's address. |
| 28 | `main.py:52-54` | Swagger, ReDoc and the OpenAPI schema are public in production. | L | Off by default when `APP_ENV=production` (`API_DOCS_ENABLED`). |
| 29 | `.env.example` | 14 settings are undocumented (`DATABASE_URL`, `UPLOAD_DIR`, `JWT_ALGORITHM`, `BOOTSTRAP_ADMIN_*`, …). | L | All documented; a test fails if a setting is missing from `.env.example`. |
| 30 | `Dockerfile:21-22`, `.env.example:61` | At start-up the embedding model contacts the Hugging Face Hub, and the shipped service catalogue probes internet hosts; offline, probes fail and tickets escalate instead of reusing verified fixes. | L | `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` after the model is baked into the image; outside Docker the embedder loads the cached model first and downloads only on the very first run. `AGENT_TOOLS_ENABLED=false` in `.env.example` until the catalogue lists real internal endpoints. |

### Dependencies (`pip-audit`, `npm audit`)

| # | Package | Advisory | Fix |
|---|---|---|---|
| 31 | `python-jose` 3.5.0 (+ `ecdsa` 0.19.2) | PYSEC-2026-4298 (HMAC key confusion), PYSEC-2026-1325 (Minerva). No fixed release. Not exploitable here (HS256 pinned), but unfixable. | Replaced by `PyJWT` (2.15); `exp`, `sub` and `type` are required claims. `ecdsa`, `rsa`, `pyasn1` drop out. |
| 32 | `filelock` 3.32.3, `setuptools` 78.1.0 | 3 CVEs / 3 advisories; stale copies pulled from the PyTorch CPU index. | Security floors `filelock>=4.2.1`, `setuptools>=84.1.0` in `requirements.txt`. |
| 33 | `vite` 8.3.1, `source-map-js` 1.2.1 | 2 high (dev server / build time only). | `npm audit fix` (patch releases). |

After the fixes `pip-audit` (installed environment, CPU torch skipped because it is not on PyPI) and
`npm audit` both report **0 known vulnerabilities**. Only patch / minor releases were taken; no package changed
major version except `filelock` 3 → 4, whose `FileLock` API is unchanged (the full test suite passes).

Secrets: the full history (6 commits) contains no keys or tokens; only `.env.example` was ever committed;
`.env` and `backend/.env` are git-ignored. `test_no_secrets_in_tracked_files` scans every tracked file for API-key
and private-key patterns, and `test_env_example_documents_every_setting` fails if a setting is added without
documenting it in `.env.example`.

## Checked and already sound

* SQL is built with SQLAlchemy expressions everywhere (no string-formatted queries).
* React escapes all rendered text; the in-house Markdown renderer produces React nodes and never sets HTML.
* There is no tool that runs arbitrary shell commands; SAFE probes take validated host names and a fixed argv.
* Employees can read only their own tickets, attachments and approvals; internal notes and escalation packages
  are staff-only.
* Passwords are bcrypt-hashed (12 rounds); logs redact secret-like fields.

## Residual risks (accepted, documented)

* Tokens live in `localStorage`, so an XSS bug would expose them. Mitigated by a CSP that allows no inline or
  third-party script, 60-minute access tokens and refresh rotation. Moving to `httpOnly` cookies would need
  CSRF protection and is the next step.
* Self-registration (needed for the demo) reveals whether a username or email is taken. It is rate-limited and
  can be switched off with `ALLOW_SELF_REGISTRATION=false`.
* Per-IP and per-user rate limits are kept in process memory. The app runs one worker by design (FAISS is
  in-process); account lockouts are stored in the database.
* `/docs` loads Swagger UI from a CDN and needs internet; the app itself does not.
* Restricted device actions remain a dry run until a real connector is configured.
* Account lockout can be used to lock a known colleague out for 15 minutes by guessing wrong on purpose. This is
  the usual trade-off of per-account lockout; the per-IP budget limits how many accounts one client can do this to.
