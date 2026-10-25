---
title: Server disk space alert on an application or file server
category: Server
doc_type: runbook
owner: Server Operations
last_reviewed: 2026-08-12
applies_to: Windows and Linux servers monitored by Zabbix; for application owners and IT staff
---

# Server disk space alert on an application or file server

Monitoring raises a warning at 85% and a critical alert at 95% disk use. Most alerts are caused by log files that are not rotated, old backups kept on the same disk, or an export left in a temporary folder.

## Symptoms
- A Zabbix alert email: "Free disk space is less than 15% on volume D:".
- The application writes errors such as "No space left on device" or "Disk full".
- File uploads in an application fail for all users.

## Resolution
1. Note the server name, volume and current percentage from the alert email.
2. Application owners: check the application's own export or upload folder for large temporary files you created and remove the ones you no longer need.
3. Check whether a large file copy or report export is running right now; it may finish and free space by itself.
4. Do not delete log or database files on the server yourself; Server Operations archives them safely.
5. Raise the ticket with the alert text attached so Server Operations can extend the volume or clean up.

## Escalation criteria
Escalate to Server Operations when:
- Disk use is above 95% or rising more than 5% per hour (critical).
- The volume holds a database; the Database Team is informed as well.
- The same server alerts more than twice in a month (capacity planning).
