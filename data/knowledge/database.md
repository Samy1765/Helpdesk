---
title: Database Access and Performance
category: Database
doc_type: runbook
---

# Database Access and Performance

## Cannot connect or log in to a database
1. Confirm you are on the office network or connected to VPN; database listeners are not exposed to the internet.
2. Check you are using the correct server name and database from the data catalog entry for the system.
3. If you see "permission denied" or "login failed for user", request access through the access request portal with your manager's approval.
4. Reporting tools cache credentials; after a password change, update the saved credentials in the tool.

## Queries are slow or timing out
1. Check whether the query filters on indexed columns and avoid SELECT * on large tables.
2. Run heavy reports outside business hours or against the reporting replica, not production.
3. If a query that used to be fast is suddenly slow for everyone, report it - the Database team will check locks and plans.

## Production database appears down
This is always handled by the Database team. Report the application affected, the error message and the time.
