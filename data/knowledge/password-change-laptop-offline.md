---
title: Laptop still accepts only the old password after a password change
category: Password
doc_type: runbook
owner: Identity & Access Team
last_reviewed: 2026-07-22
applies_to: Windows 11 laptops used mainly from home
---

# Laptop still accepts only the old password after a password change

Windows remembers the password it last checked with the company network. If you change your password on the web or another device while the laptop is offline, the laptop keeps expecting the old one until it reaches the network again.

## Symptoms
- The laptop sign-in screen accepts the old password, but Outlook and Teams want the new one.
- "Your password has expired" keeps appearing even though you changed it.
- File shares ask for credentials after you sign in.

## Resolution
1. Sign in to the laptop with the old password.
2. Connect to Wi-Fi and then GlobalProtect VPN using your new password at the VPN prompt.
3. With the VPN connected, lock the laptop (Windows key + L) and unlock it with the new password.
4. Restart the laptop while still on the office network or VPN, then sign in with the new password.
5. Sign out of and back in to Outlook, Teams and OneDrive.

## Escalation criteria
Escalate to the Identity & Access Team when:
- The laptop refuses both the old and the new password.
- The VPN rejects the new password after the steps above.
