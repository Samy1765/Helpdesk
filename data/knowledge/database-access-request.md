---
title: Requesting Database and Reporting Access
category: Database
doc_type: runbook
last_reviewed: 2026-09-19
owner: Database Team
---

# Requesting Database and Reporting Access

## Which access do you need?
| Need | Access to request | Approver |
|---|---|---|
| View dashboards | Reporting viewer | Manager |
| Run your own queries on reporting copies | Analytics read-only | Manager and data owner |
| Read production data | Production read-only (time-limited) | Data owner and Database Team |
| Change production data | Not granted to individuals; use a change request | Change board |

## Requesting access
1. Raise an access request in the IT portal, choosing "Database access".
2. Name the database or report, the access level from the table above and the business reason.
3. Personal data (HR, payroll, customer records) also needs a short justification for the data protection review.
4. Access is granted to your company account; shared logins are not issued.

## After approval
1. Sign in to the database tools with your company account. Do not create or ask for local database passwords.
2. Production read-only access expires after 30 days. Request it again if you still need it.

## "Login failed for user" after approval
1. Sign out of the tool and sign in again; group membership is only read at sign-in.
2. Wait up to one hour after the approval email for access to apply.
3. Check that you are connecting to the database named in the approval (reporting copy or production).

## When to escalate
Raise a ticket for the Database Team if access is still refused two hours after approval.
