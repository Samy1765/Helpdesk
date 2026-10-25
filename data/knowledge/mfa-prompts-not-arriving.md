---
title: Authenticator notifications do not arrive or codes are rejected
category: Password
doc_type: runbook
owner: Identity & Access Team
last_reviewed: 2026-09-01
applies_to: Microsoft Authenticator with number matching
---

# Authenticator notifications do not arrive or codes are rejected

Missing notifications are usually caused by phone battery optimisation, notifications switched off for Authenticator, or a phone clock that is wrong (codes then fail).

## Symptoms
- Sign-in waits for approval but nothing appears on the phone.
- The six-digit code from Authenticator is rejected.
- Approvals work on Wi-Fi but not on mobile data.

## Resolution
1. Open the Authenticator app itself; pending requests often appear inside the app even when the notification did not.
2. Allow notifications for Authenticator in the phone settings and turn off battery optimisation for the app.
3. Set the phone's date and time to automatic; codes fail when the clock is off by more than 30 seconds.
4. On the sign-in screen choose "I can't use my Authenticator app right now" and use the text-message option instead.
5. Update the Authenticator app from the app store and try again.

## Escalation criteria
Escalate to the Identity & Access Team when:
- No verification method works and you cannot sign in at all.
- You receive approval requests you did not start; deny them and report it at once, as your password may be known to someone else.
