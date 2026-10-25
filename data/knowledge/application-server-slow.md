---
title: Internal application is very slow for everyone
category: Server
doc_type: runbook
owner: Server Operations
last_reviewed: 2026-09-26
applies_to: Acme ERP (web), Acme Connect and reporting portals
---

# Internal application is very slow for everyone

When an internal application slows down for many users at the same time, the cause is usually on the server side: high CPU or memory on the application server, a long-running report, or a database lock.

## Symptoms
- Pages take more than 20 seconds to load for several people.
- Reports that normally run in seconds time out.
- The slowness started at the same time for a whole team.

## Resolution
1. Check https://status.acme-demo.in for planned maintenance or a known issue.
2. Ask two colleagues whether they see the same slowness, to rule out your laptop or network.
3. Avoid starting large reports or exports again while the system is slow; repeated runs make it worse.
4. Note which screen or report is slow, the time it started and an approximate number of affected users.
5. Raise one ticket for the team rather than one per person; colleagues can add themselves as affected.

## Escalation criteria
Escalate to Server Operations when:
- More than five users or a whole site are affected (high priority).
- Month-end, payroll or a production line depends on the application (critical priority).
- Slowness started right after a planned change; mention the change number from the status page.
