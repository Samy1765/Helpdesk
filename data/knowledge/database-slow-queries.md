---
title: Slow Reports and Query Timeouts
category: Database
doc_type: runbook
last_reviewed: 2026-08-31
owner: Database Team
---

# Slow Reports and Query Timeouts

## Symptoms
- A report or dashboard that usually loads in seconds now takes minutes or times out.
- Your query fails with "timeout expired" or "canceling statement due to statement timeout".

## Checks for report users
1. Check the IT status page for planned maintenance or data loads; overnight loads sometimes overrun into the morning.
2. Narrow the date range or filters; a report across several years can take much longer than one for the current month.
3. Try again after 15 minutes. If the report is fast later, the slowdown was caused by load, not a fault.

## Checks for people who write queries
1. Run queries on the reporting copy, not on production.
2. Filter on indexed columns, usually dates and IDs, and avoid functions on those columns in WHERE clauses.
3. Avoid `SELECT *` on wide tables; select only the columns you need.
4. Check the query plan for full table scans on large tables.
5. Close idle sessions in your SQL tool; long-open transactions can block other users.

## Never
Do not ask for timeouts to be removed, and do not run heavy queries against production during business hours.

## When to escalate
Raise a ticket for the Database Team with the report name or query, the time it was run and the error text if a report that was fast yesterday is slow for everyone today. Mark it high priority if a business process such as payroll or invoicing is blocked.
