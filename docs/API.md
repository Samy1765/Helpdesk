# API reference

* Interactive docs: **http://localhost:8000/docs** (Swagger — click *Authorize* and log in) or `/redoc`.
* Machine-readable spec: [`openapi.json`](openapi.json) (regenerate: `python -c "import json; from app.main import app; print(json.dumps(app.openapi()))" > ../docs/openapi.json`).
* All endpoints are under `/api/v1`, JSON in/out, `Authorization: Bearer <access_token>` unless noted.
* Swagger, ReDoc and `openapi.json` are served in development and test; in production only with `API_DOCS_ENABLED=true`.
* Every endpoint for IT staff or administrators checks the role server-side; `tests/test_security.py` calls each one as an employee (and the admin ones as IT support) and expects `403`.

## Authentication
| Method | Path | Who | Notes |
|---|---|---|---|
| POST | `/auth/register` | public | always creates an **employee**; returns tokens + user. `403` when `ALLOW_SELF_REGISTRATION=false`, `429` over the per-IP budget |
| POST | `/auth/login` | public | `{username (or email), password}` → access + refresh tokens and a new session. Same `401` for unknown user and wrong password; `429` + `Retry-After` when the account or the client IP is locked out |
| POST | `/auth/token` | public | OAuth2 form flow (Swagger), same rules as login |
| POST | `/auth/refresh` | public | `{refresh_token}` → a new pair; the old refresh token stops working (rotation). Replaying a replaced token ends the session |
| POST | `/auth/logout` | any | revokes the session: both tokens stop working immediately |
| GET/PATCH | `/auth/me` | any | profile; employees may pick a business unit, IT team membership is admin-only |
| POST | `/auth/change-password` | any | signs out every session and returns tokens for a fresh one; wrong current passwords are throttled |

## Chatbot
| Method | Path | Notes |
|---|---|---|
| GET | `/chat/conversation` | active conversation + messages (with structured `payload` cards) |
| POST | `/chat/message` | `{message, user_priority?, client_env?, attachment_tokens?}` → reply with `stage`, `quick_replies`, `payload` (alerts, progress, ticket, solution, approvals, escalation, incident, duplicate, similar, priority_assessment) |
| POST | `/chat/new` | close the active conversation and start fresh |
| POST | `/attachments` | multipart `file` (+ optional `ticket_id`); PNG, JPG, GIF, WEBP, PDF, TXT, LOG ≤ 5 MB. The file's bytes must match its extension (`415` otherwise); it is stored under a random name |
| GET | `/attachments/{token}` | owner, IT staff, or the requester of the ticket it is attached to; always sent as a download |

`/chat/message` and `POST /tickets` share a per-user budget (`RATE_LIMIT_CHAT_PER_MINUTE`, `429` when exceeded).

## Tickets
| Method | Path | Who | Notes |
|---|---|---|---|
| GET | `/tickets` | any | role-filtered; `status, category, priority, q, scope(default/open/closed/all), page, per_page` |
| POST | `/tickets` | any | portal form; same classification/priority/agent pipeline as chat |
| GET | `/tickets/{id}` | owner / staff | ticket, messages, execution steps, events, agent state/progress, current solution, actions, escalation (package staff-only), incident, duplicate, similar, attachments |
| POST | `/tickets/{id}/feedback` | requester | `{resolved, comment?}` → RESOLVED / RETRY / ESCALATE |
| POST | `/tickets/{id}/rating` | requester | `{rating: 1-5, comment?}` once the ticket is resolved or closed; a new rating replaces the previous one |
| POST | `/tickets/{id}/comments` | owner / staff | `{content, internal}` (internal = staff only) |
| POST | `/tickets/{id}/request-human` | owner / staff | stop the agent and escalate |

## Approvals
| Method | Path | Notes |
|---|---|---|
| GET | `/actions/pending` | employees see their own; staff see all (`can_decide` flag) |
| POST | `/actions/{id}/decision` | `{approve}`; restricted → requester or staff, dangerous → admin |

## Incidents
| Method | Path | Who |
|---|---|---|
| GET | `/incidents?state=active\|resolved\|all` | any (status page) |
| GET | `/incidents/{id}` | any; linked tickets & timeline for staff, own tickets for employees |
| PATCH | `/incidents/{id}` | staff: `status`, `root_cause` |
| POST | `/incidents/{id}/resolve` | staff: resolves every linked open ticket and stores a human-verified solution |
| POST | `/incidents/{id}/link` | staff: manually link a ticket |

## Knowledge base
| Method | Path | Who |
|---|---|---|
| GET | `/knowledge/documents?q&category_id` | any |
| GET | `/knowledge/documents/{id}` | any |
| GET | `/knowledge/search?q=` | any — semantic search over verified solutions + docs |
| POST/PATCH | `/knowledge/documents[/{id}]` | staff (chunked + indexed immediately) |

## IT support (staff)
`GET /support/overview`, `GET /support/queue?view=unassigned|mine|escalated|ai_active|critical|all_open|resolved|duplicates`, `GET /support/agents`, `POST /support/tickets/{id}/accept|assign|status|steps|resolve`, `PATCH /support/tickets/{id}/classification`, `GET|POST /support/solutions`, `POST /support/solutions/{id}/verify|reject`.

## Admin
`GET /admin/analytics?days=` (adds `sla`: compliance by priority and open breaches, `satisfaction`: ratings, `approvals`: approved / declined / waiting), `GET /admin/users`, `PATCH /admin/users/{id}` (role, department and activation changes are audited; deactivation ends the user's sessions), `POST /admin/categories`, `GET /admin/system`, `POST /admin/index/rebuild`, `GET /admin/audit-logs`, `GET /admin/llm-calls`, `GET /admin/departments`.

## Shared
`GET /dashboard` (role-aware), `GET /notifications`, `GET /meta/categories`, `GET /meta/departments`, `GET /health` (no auth).

## Example: full chat flow with curl

```bash
TOKEN=$(curl -s localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"johndoe","password":"Employee@123"}' | jq -r .access_token)
H="Authorization: Bearer $TOKEN"

curl -s localhost:8000/api/v1/chat/new -X POST -H "$H"
curl -s localhost:8000/api/v1/chat/message -H "$H" -H 'Content-Type: application/json' \
  -d '{"message":"GlobalProtect fails right after I approve the sign-in on my phone"}' | jq '.stage, .message, .quick_replies'
curl -s localhost:8000/api/v1/chat/message -H "$H" -H 'Content-Type: application/json' \
  -d '{"message":"Just me"}' | jq '.ticket_number, .payload.solution.label, .payload.agent'
curl -s localhost:8000/api/v1/chat/message -H "$H" -H 'Content-Type: application/json' \
  -d '{"message":"Yes, it is fixed"}' | jq '.payload.agent.state'
```
