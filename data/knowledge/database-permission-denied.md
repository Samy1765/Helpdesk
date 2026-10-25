---
title: Permission denied on a database table or schema
category: Database
doc_type: guide
owner: Database Team
last_reviewed: 2026-07-25
applies_to: Reporting databases; access follows the data classification policy
---

# Permission denied on a database table or schema

Access to reporting data is granted per schema, based on the data classification (Public, Internal, Confidential). Confidential schemas such as payroll need the data owner's approval in addition to your manager's.

## Symptoms
- "The SELECT permission was denied on the object" (SQL Server).
- "permission denied for schema finance" or "for table ..." (PostgreSQL).
- A colleague in the same team can read a table you cannot.

## Resolution
1. Copy the exact error message, including the schema and table name.
2. In the Company Portal, open "Request access" > "Reporting database access" and name the schema you need.
3. Explain what the data is used for; confidential schemas are approved by the data owner listed on the Analytics page of Acme Connect.
4. Once you receive the approval email, disconnect from the database and connect again.
5. Do not ask colleagues to share query results from confidential schemas while you wait for access.

## Escalation criteria
Escalate to the Database Team when:
- Approved access is still denied after reconnecting.
- A permission change removed access for a whole team.
Report to the Security Team if you can read data you should not have access to.
