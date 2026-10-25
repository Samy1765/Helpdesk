---
title: VPN Blocked by Device Compliance Check
category: VPN
doc_type: runbook
last_reviewed: 2026-08-29
owner: Network Team
---

# VPN Blocked by Device Compliance Check

## Symptoms
- The VPN client signs in and then shows "Device not compliant" or "Posture assessment failed".
- The connection stops at "Checking system requirements".

## Why it happens
Before allowing a tunnel, the gateway checks that the laptop has disk encryption switched on, a supported operating system build, current antivirus definitions and the company certificate. Any one missing item blocks the connection. Pending updates are the most common cause.

## Steps
1. Install all pending operating system updates and restart the laptop, even if no restart is requested.
2. Open the antivirus console and run "Update definitions"; wait until it reports up to date.
3. Confirm the laptop is still joined to the company: the sign-in screen should show your company account, not a local one.
4. Reconnect the VPN and let the compliance check finish (it can take up to two minutes on the first attempt after updates).
5. Never switch off antivirus or disk encryption to get past the check. That will not work and will be reported to the Security Team.

## When to escalate
If the client still reports non-compliance after updates, raise a ticket for the Network Team with a screenshot of the compliance message. A missing or expired device certificate can only be reissued by IT.
