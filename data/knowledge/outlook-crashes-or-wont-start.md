---
title: Outlook crashes, freezes or will not start
category: Email
doc_type: runbook
owner: Email & Collaboration Team
last_reviewed: 2026-09-18
applies_to: Outlook for Microsoft 365 (classic) on Windows 11
---

# Outlook crashes, freezes or will not start

Crashes after a monthly Office update are usually caused by an add-in that has not been updated yet. A damaged offline cache (OST file) causes freezes at "Loading profile".

## Symptoms
- Outlook closes a few seconds after opening, sometimes with "Microsoft Outlook has stopped working".
- Outlook stays on "Loading profile" or "Processing".
- Outlook shows "Not responding" whenever a particular email is opened.

## Resolution
1. Close Outlook and check in Task Manager (Ctrl+Shift+Esc) that no OUTLOOK.EXE process is left; end it if it is.
2. Start Outlook in safe mode: hold Ctrl while clicking the Outlook icon and confirm the prompt.
3. If safe mode works, go to File > Options > Add-ins > Manage: COM Add-ins > Go, untick add-ins installed recently, then restart Outlook normally.
4. Clear the Outlook cache. The helpdesk agent can do this for you with your approval; Outlook rebuilds it from the server.
5. While IT investigates, use Outlook on the web at https://outlook.office.com so you can keep working.

## Escalation criteria
Escalate to the Email & Collaboration Team when:
- Outlook crashes in safe mode as well (the Office installation needs a repair).
- The crash started for many users on the same day (likely a faulty update ring).
- A specific message crashes Outlook every time; do not forward it, mention its subject in the ticket.
