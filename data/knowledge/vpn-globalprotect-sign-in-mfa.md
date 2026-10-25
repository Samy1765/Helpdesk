---
title: GlobalProtect VPN fails at sign-in or MFA approval
category: VPN
doc_type: runbook
owner: Network Team
last_reviewed: 2026-09-22
applies_to: Windows 11 and macOS laptops, GlobalProtect 6.2, portal vpn.acme-demo.in
---

# GlobalProtect VPN fails at sign-in or MFA approval

Most sign-in failures come from an expired single sign-on session cached by the GlobalProtect agent, a device clock that has drifted, or a VPN entitlement that lapsed after a role change.

## Symptoms
- GlobalProtect shows "Authentication failed" straight after the Microsoft Authenticator prompt.
- The sign-in window closes and the agent goes back to "Not connected" without an error.
- The portal reports "Gateway vpn.acme-demo.in: user not authorised".

## Resolution
1. Right-click the GlobalProtect icon in the system tray (menu bar on macOS) and choose Disconnect, then Sign Out.
2. Open https://myaccount.acme-demo.in in a browser and sign in, so a fresh single sign-on session is created.
3. Check that the laptop clock is set automatically: Settings > Time & language > Date & time > Set time automatically.
4. Reopen GlobalProtect, choose Connect, and approve the Authenticator notification within 60 seconds. Type the two-digit number shown on the laptop.
5. If the portal says you are not authorised, request "Remote access (VPN)" in the Company Portal; your line manager approves it.

## Escalation criteria
Escalate to the Network Team when:
- The steps above fail on two different networks (home Wi-Fi and a phone hotspot).
- More than three colleagues report the same error within an hour (possible gateway or identity-provider fault).
- The VPN entitlement shows as approved but the gateway still rejects the account.
