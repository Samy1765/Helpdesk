---
title: Queries or reports time out on the reporting database
category: Database
doc_type: runbook
owner: Database Team
last_reviewed: 2026-09-17
applies_to: ERP reporting replica and analytics PostgreSQL; for analysts and report developers
---

# Queries or reports time out on the reporting database

Timeouts usually come from a query that scans a whole large table, a report running at the same time as the nightly data load (01:00 to 04:00 IST), or locks held by another long-running query.

## Symptoms
- A query that took seconds last week now runs for minutes or times out.
- Errors such as "Execution Timeout Expired" or "canceling statement due to statement timeout".
- Reports are slow only early in the morning.

## Resolution
1. Avoid running heavy reports between 01:00 and 04:00 IST while the nightly load runs.
2. Add a date filter to the query so it reads only the period you need, for example the current financial year.
3. Select only the columns you need instead of SELECT * on large tables.
4. Cancel queries you no longer need in your SQL tool, so they release their locks.
5. Note the report name, query text and the time it ran, and attach them to the ticket.

## Escalation criteria
Escalate to the Database Team when:
- A query that used to run quickly is slow for several users without any change on their side.
- Errors mention deadlocks or blocking sessions.
- Production systems slow down at the same time as reports (critical priority).
