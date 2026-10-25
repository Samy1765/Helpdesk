---
title: Move Microsoft Authenticator to a new phone
category: Password
doc_type: guide
owner: Identity & Access Team
last_reviewed: 2026-08-19
applies_to: Microsoft Authenticator on Android and iOS
---

# Move Microsoft Authenticator to a new phone

Do this before you reset or hand in the old phone. If the old phone is already gone, the Identity & Access Team has to verify your identity and reset your MFA registration.

## Symptoms
- You have a new phone and the Authenticator app on it shows no work account.
- Sign-in asks you to approve a request on a phone you no longer have.
- Authenticator says "Account action required".

## Resolution
1. On a laptop, open https://myaccount.acme-demo.in > Security info while the old phone still works.
2. Choose "Add sign-in method" > Authenticator app, and scan the QR code with the Authenticator app on the new phone.
3. Approve the test notification on the new phone, then set it as the default sign-in method.
4. Delete the old phone from the Security info list.
5. Sign in to Outlook on the web once to confirm the new phone receives the notification.

## Escalation criteria
Escalate to the Identity & Access Team when:
- The old phone is lost, broken or already reset; bring your employee ID card to the service desk or join a video call for identity verification.
- Security info shows a sign-in method you did not add (the Security Team is informed).
