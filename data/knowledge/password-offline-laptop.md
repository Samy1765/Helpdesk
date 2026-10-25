---
title: Laptop Still Wants the Old Password After a Change
category: Password
doc_type: runbook
last_reviewed: 2026-08-12
owner: Identity & Access Team
---

# Laptop Still Wants the Old Password After a Change

## Symptoms
- You changed your password from a browser or phone, and the laptop sign-in screen only accepts the old one.
- Outlook, Teams or the file shares keep asking for credentials after a password change.
- Your account locks repeatedly a few minutes after it is unlocked.

## Why it happens
A laptop remembers the last password it saw from the company network. It only learns the new password when it can reach the company directory, in the office or over the VPN.

## Steps
1. Sign in to the laptop with your old password.
2. Connect to the VPN (or plug into the office network).
3. Lock the screen (Windows key + L) and unlock it with your new password. This updates the cached password.
4. Restart Outlook and Teams and sign in with the new password when asked.
5. Open Credential Manager in Windows and remove saved entries for company services that still hold the old password.
6. Update the password on your phone mail app and any tablet; old passwords on these devices are the usual cause of repeated lockouts.

## When to escalate
If your account keeps locking even after updating all devices, ask the helpdesk agent to unlock it (needs your approval) and raise a ticket so the Identity & Access Team can see which device is sending the old password.
