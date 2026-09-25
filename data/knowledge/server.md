---
title: Server and Service Operations Runbook
category: Server
doc_type: runbook
---

# Server and Service Operations

## Reporting a service outage
Employees cannot fix server outages; the goal is to give Server Operations the right facts quickly.
1. Note the exact URL or service name, the time the problem started, and the error message or HTTP code.
2. Check whether colleagues are affected; outages affecting many users are grouped into one incident automatically.
3. Check the IT status page for an existing incident before reporting.

## Slow application servers
1. Note which pages or actions are slow and how long they take.
2. Compare from the office network and from VPN; if only VPN is slow, report it as a VPN issue.

## Disk space alerts (for server owners)
1. Identify the volume and growth trend in the monitoring dashboard.
2. Rotate and compress application logs following the log retention policy.
3. Never delete data files or database files to free space; open a change request with Server Operations.
