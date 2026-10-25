---
title: Reset a forgotten or expired password
category: Password
doc_type: runbook
owner: Identity & Access Team
last_reviewed: 2026-10-06
applies_to: Company accounts (name@acme-demo.in); passwords expire every 180 days
---

# Reset a forgotten or expired password

Every employee can reset their own password at https://myaccount.acme-demo.in after verifying with the Authenticator app or the registered mobile number. The service desk never needs to know your password.

## Symptoms
- Windows says "The user name or password is incorrect" although you are sure of the password.
- Outlook or the VPN says "Your password has expired".
- You have forgotten the password after leave or a long weekend.

## Resolution
1. From any browser (phone or another laptop), open https://myaccount.acme-demo.in and choose "Forgot my password".
2. Verify with the Authenticator notification or the text message sent to your registered mobile.
3. Choose a new password of at least 14 characters; a short sentence is easier to remember than random characters.
4. On the laptop, connect to the office network or VPN, press Ctrl+Alt+Del and sign in with the new password so Windows caches it.
5. Sign out of Outlook, Teams and OneDrive and sign in again with the new password.

## Escalation criteria
Escalate to the Identity & Access Team when:
- Self-service reset says your account is not registered for verification.
- The reset succeeds but the new password is rejected everywhere for more than 30 minutes.
- You no longer have the phone registered for verification (identity check required).
