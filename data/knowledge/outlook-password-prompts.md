---
title: Outlook or Teams keeps asking you to sign in
category: Email
doc_type: runbook
owner: Email & Collaboration Team
last_reviewed: 2026-08-26
applies_to: Microsoft 365 apps on company laptops
---

# Outlook or Teams keeps asking you to sign in

Repeated sign-in windows normally mean the saved credential no longer matches your current password (for example, after a reset on your phone), or the Office sign-in token has expired.

## Symptoms
- Outlook shows "Need password" in the status bar, or a sign-in window that comes back after you complete it.
- Teams and OneDrive also show "Sign in required".
- Outlook on the web works normally.

## Resolution
1. Lock the laptop (Windows key + L) and unlock it with your current password so Windows picks up the new credential.
2. In Outlook, go to File > Office Account and choose Sign out, then close every Office app.
3. Open Outlook again and sign in with your company email address; approve the Authenticator prompt.
4. If your password was changed recently on another device, connect to the office network or VPN first so the laptop can confirm the new password.
5. Check https://myaccount.acme-demo.in: if it says your password has expired, change it there first.

## Escalation criteria
Escalate to the Email & Collaboration Team when:
- Prompts continue after signing out and back in with a confirmed working password.
- Only one Office app keeps prompting while the others work.
Escalate to the Identity & Access Team when the account shows as locked or disabled.
