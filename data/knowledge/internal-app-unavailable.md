---
title: Internal application shows 502, 503 or "service unavailable"
category: Server
doc_type: runbook
owner: Server Operations
last_reviewed: 2026-09-19
applies_to: Acme ERP (web), Acme Connect intranet, HR portal and other apps behind apps.acme-demo.in
---

# Internal application shows 502, 503 or "service unavailable"

A 502 or 503 page means the application server behind the load balancer is not answering. One person cannot fix this from their laptop, but a quick check tells IT whether it affects everyone.

## Symptoms
- The browser shows "502 Bad Gateway", "503 Service Unavailable" or "504 Gateway Timeout".
- The application loads the login page but fails after sign-in with a server error.
- Colleagues report the same page at the same time.

## Resolution
1. Check https://status.acme-demo.in; planned maintenance and known outages are listed there.
2. Reload the page once after two minutes; deployments can briefly return 503.
3. Ask a colleague, or try from another network (VPN off and on), to see whether it affects only you.
4. If only you are affected, clear the site cookies and try a private browser window.
5. Report it with the application name, the exact error page, the time and how many people are affected.

## Escalation criteria
Escalate to Server Operations when:
- More than one user sees the error, or the status page shows no known issue after five minutes.
- A business-critical application (ERP, payroll, plant MES) is down during working hours; this is critical priority.
- The error appears during month-end closing or payroll runs.
