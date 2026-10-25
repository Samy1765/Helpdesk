---
title: Office Wi-Fi Sign-in and Certificate Prompts
category: Network
doc_type: runbook
last_reviewed: 2026-09-10
owner: Network Team
---

# Office Wi-Fi Sign-in and Certificate Prompts

## Networks in our offices
| Network | Who uses it | How it signs in |
|---|---|---|
| ACME-CORP | Company laptops | Automatically, using the device certificate |
| ACME-BYOD | Personal phones and tablets | Company account and MFA |
| ACME-GUEST | Visitors | Daily code from reception, internet only |

## Company laptop will not join ACME-CORP
1. Make sure you are choosing ACME-CORP, not ACME-GUEST; the guest network cannot reach internal systems.
2. Select ACME-CORP, choose "Forget", then join it again. The laptop should connect without asking for a password.
3. If you are asked to trust a certificate, check that the server name ends in our company domain before accepting. If it does not, cancel and report it to the Security Team.
4. Restart the laptop while connected to a wired port or the VPN so it can renew its device certificate, then try the Wi-Fi again.

## Phone will not join ACME-BYOD
1. Forget the network on the phone and join again with your full company email address.
2. Approve the MFA request on your authenticator app.
3. If your password changed recently, the phone may still try the old one and lock your account; update it in the Wi-Fi settings.

## When to escalate
Escalate to the Network Team if the laptop cannot join ACME-CORP after a restart on a wired connection, or if a whole floor loses Wi-Fi.
