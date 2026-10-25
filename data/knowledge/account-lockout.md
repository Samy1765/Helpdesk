---
title: Account locked after several wrong password attempts
category: Password
doc_type: runbook
owner: Identity & Access Team
last_reviewed: 2026-10-06
applies_to: Company accounts; lockout after 10 failed attempts, automatic unlock after 30 minutes
---

# Account locked after several wrong password attempts

Accounts lock after 10 wrong passwords and unlock themselves after 30 minutes. Lockouts that keep coming back are almost always a phone or laptop still trying an old password in the background.

## Symptoms
- Windows or the self-service portal shows "Your account has been locked".
- You changed your password yesterday and today the account locks again within minutes.
- Email stops syncing on your phone at the same time.

## Resolution
1. Unlock the account at https://myaccount.acme-demo.in > "Unlock account", verifying with the Authenticator app. The helpdesk agent can also unlock it after you approve the request.
2. If you changed your password recently, update it on your phone: Outlook app > Settings > your account > re-enter the password, and the same for Teams.
3. Remove saved Wi-Fi networks that use your account on personal devices, and old mapped drives on the laptop.
4. Sign out of any shared or meeting-room PC you used before the password change.
5. Wait 15 minutes and confirm the lockout does not return.

## Escalation criteria
Escalate to the Identity & Access Team when:
- The account locks again within an hour after the steps above.
- Lockouts happen while you were not working (possible password-guessing attempt; Security is informed too).
- The unlock option is not offered for your account.
