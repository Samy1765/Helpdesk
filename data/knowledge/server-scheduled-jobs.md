---
title: Scheduled Job or Batch Process Did Not Run
category: Server
doc_type: runbook
last_reviewed: 2026-09-27
owner: Server Operations
---

# Scheduled Job or Batch Process Did Not Run

## Symptoms
- A daily report, data export or file transfer did not arrive.
- A dashboard shows yesterday's data.
- The job monitor shows a job as failed, skipped or still running.

## Information to collect
1. The job or report name exactly as it appears in the job monitor or in the email you normally receive.
2. When it normally runs and when you noticed it was missing.
3. Whether other reports from the same system arrived.

## Steps for employees
1. Check the IT status page for maintenance on the source system.
2. Do not request a manual rerun of finance or payroll jobs yourself; reruns can create duplicate payments or postings. Raise a ticket instead.

## Steps for Server Operations
1. Open the job's last run log and note the failing step and the error.
2. Check that upstream dependencies finished: source extracts, file drops and database availability.
3. Check disk space on the job server and the target location.
4. Check credentials used by the job; expired service account passwords and certificates are a frequent cause.
5. Rerun only after confirming the job can safely run twice, and tell the business owner when data is available.

## When to escalate
Missing finance, payroll or regulatory jobs are high priority, or critical if a deadline falls on the same day. Escalate to the system owner as well as Server Operations.
