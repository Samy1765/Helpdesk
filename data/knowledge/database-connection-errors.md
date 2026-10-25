---
title: Cannot Connect to a Database
category: Database
doc_type: runbook
last_reviewed: 2026-09-09
owner: Database Team
---

# Cannot Connect to a Database

## Common errors and what they mean
| Error | Usual cause |
|---|---|
| Connection refused / could not connect to server | Not on the office network or VPN, or the server is down |
| Connection timed out | Firewall rule missing for your network, or VPN not connected |
| SSL / certificate error | Old client or driver that does not trust the current certificate |
| Too many connections | The server's connection limit is reached, usually by an application |
| Login failed | Access not granted yet, or wrong database name |

## Steps
1. Connect to the VPN if you are not in the office. Databases are never reachable from the internet.
2. Check the host name and database name against the connection details in the data catalogue; reporting copies and production have different names.
3. Update your SQL tool and database driver to the versions in Software Center to fix certificate errors.
4. Close unused tabs and sessions in your SQL tool; each one holds a connection.
5. Check the IT status page for database maintenance.

## For application owners
If an application reports "too many connections", check its connection pool settings and look for connections that are opened but never closed. Restarting the application frees connections only temporarily.

## When to escalate
Raise a ticket for the Database Team with the exact error text, the host name and the time. Mark it critical if a production application cannot reach its database.
