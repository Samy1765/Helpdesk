---
title: Internal Web Application Shows 502, 503 or 504 Errors
category: Server
doc_type: runbook
last_reviewed: 2026-09-22
owner: Server Operations
---

# Internal Web Application Shows 502, 503 or 504 Errors

## What the errors mean
- **502 Bad Gateway**: the load balancer reached the application server, but the application did not answer properly.
- **503 Service Unavailable**: the application is stopped, overloaded or in maintenance.
- **504 Gateway Timeout**: the application took too long to respond.
These are server-side errors. Clearing your browser or restarting your laptop will not fix them.

## Steps for employees
1. Check the IT status page for the application. If an incident is already open, you do not need to report it again; the page shows updates.
2. Reload the page once after a minute. Short 503s happen during planned restarts.
3. Ask a colleague to try. If it works for them, see the browser sign-in runbook instead.
4. Report it through the chat with the application name, the error number and the time. The agent checks the service status and links your report to any open incident.

## Steps for Server Operations
1. Check the application's health endpoint and the load balancer's pool status.
2. Review the last deployment time; roll back if the errors started after a release.
3. Check CPU, memory and disk on the application servers, and database connectivity.
4. Post an update on the status page within 15 minutes of confirming an outage.

## When to escalate
Any 5xx error affecting more than one person on a business-critical application is high priority; an outage of a customer-facing service is critical.
