# API reference

* Interactive docs: **http://localhost:8000/docs** (Swagger — click *Authorize* and log in) or `/redoc`.
* Machine-readable spec: [`openapi.json`](openapi.json) (regenerate: `python -c "import json; from app.main import app; print(json.dumps(app.openapi()))" > ../docs/openapi.json`).
* All endpoints are under `/api/v1`, JSON in/out, `Authorization: Bearer <access_token>` unless noted.

## Authentication
| Method | Path | Who | Notes |
|---|---|---|---|
| POST | `/auth/register` | public | always creates an **employee**; returns tokens + user |
| POST | `/auth/login` | public | `{username (or email), password}` → access + refresh tokens |
| POST | `/auth/token` | public | OAuth2 form flow (Swagger) |
| POST | `/auth/refresh` | public | `{refresh_token}`; refresh tokens cannot be used as access tokens |
| POST | `/auth/logout` | any | audited; client discards tokens |
| GET/PATCH | `/auth/me` | any | profile |
| POST | `/auth/change-password` | any | |

## Chatbot
| Method | Path | Notes |
|---|---|---|
| GET | `/chat/conversation` | active conversation + messages (with structured `payload` cards) |
| POST | `/chat/message` | `{message, user_priority?, client_env?, attachment_tokens?}` → reply with `stage`, `quick_replies`, `payload` (alerts, progress, ticket, solution, approvals, escalation, incident, duplicate, similar, priority_assessment) |
| POST | `/chat/new` | close the active conversation and start fresh |
| POST | `/attachments` | multipart `file` (+ optional `ticket_id`); images, PDF, text ≤ 5 MB |
| GET | `/attachments/{token}` | owner or IT staff |

## Tickets
| Method | Path | Who | Notes |
|---|---|---|---|
| GET | `/tickets` | any | role-filtered; `status, category, priority, q, scope(default/open/closed/all), page, per_page` |
| POST | `/tickets` | any | portal form; same classification/priority/agent pipeline as chat |
| GET | `/tickets/{id}` | owner / staff | ticket, messages, execution steps, events, agent state/progress, current solution, actions, escalation (package staff-only), incident, duplicate, similar, attachments |
| POST | `/tickets/{id}/feedback` | requester | `{resolved, comment?}` → RESOLVED / RETRY / ESCALATE |
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
`GET /admin/analytics?days=`, `GET /admin/users`, `PATCH /admin/users/{id}`, `POST /admin/categories`, `GET /admin/system`, `POST /admin/index/rebuild`, `GET /admin/audit-logs`, `GET /admin/llm-calls`, `GET /admin/departments`.

## Shared
`GET /dashboard` (role-aware), `GET /notifications`, `GET /meta/categories`, `GET /meta/departments`, `GET /health` (no auth).

## Example: full chat flow with curl

```bash
TOKEN=$(curl -s localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"johndoe","password":"Employee@123"}' | jq -r .access_token)
H="Authorization: Bearer $TOKEN"

curl -s localhost:8000/api/v1/chat/new -X POST -H "$H"
curl -s localhost:8000/api/v1/chat/message -H "$H" -H 'Content-Type: application/json' \
  -d '{"message":"My VPN times out right after I enter the 2FA code"}' | jq '.stage, .message, .quick_replies'
curl -s localhost:8000/api/v1/chat/message -H "$H" -H 'Content-Type: application/json' \
  -d '{"message":"Just me"}' | jq '.ticket_number, .payload.solution.label, .payload.agent'
curl -s localhost:8000/api/v1/chat/message -H "$H" -H 'Content-Type: application/json' \
  -d '{"message":"Yes, it is fixed"}' | jq '.payload.agent.state'
```
