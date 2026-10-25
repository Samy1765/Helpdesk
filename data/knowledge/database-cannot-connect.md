---
title: Cannot connect or log in to a reporting database
category: Database
doc_type: runbook
owner: Database Team
last_reviewed: 2026-08-24
applies_to: ERP reporting replica (SQL Server, erp-rpt.acme-demo.in:1433) and analytics PostgreSQL (pg-analytics.acme-demo.in:5432)
---

# Cannot connect or log in to a reporting database

Analysts connect to read-only reporting copies, never to production. Most connection problems are a missing VPN connection, the wrong server name, or an account that was not granted access to that database.

## Symptoms
- SQL Server Management Studio or DBeaver shows "A network-related or instance-specific error occurred".
- "Login failed for user" or "password authentication failed for user".
- Power BI refresh fails with a data source error.

## Resolution
1. Connect GlobalProtect VPN first when working outside the office.
2. Check the server name and port: erp-rpt.acme-demo.in,1433 for SQL Server or pg-analytics.acme-demo.in port 5432 for PostgreSQL.
3. Use Windows (Active Directory) authentication for SQL Server; personal SQL logins are not issued.
4. For PostgreSQL, sign in with your company username; database names are listed on the Analytics page of Acme Connect.
5. If the error says the login failed, request "Reporting database access" in the Company Portal with the database name.

## Escalation criteria
Escalate to the Database Team when:
- The server is unreachable for several analysts at once.
- Access was approved but login still fails after signing out and in.
- A scheduled Power BI refresh fails for a whole department's reports.
