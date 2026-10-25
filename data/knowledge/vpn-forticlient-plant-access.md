---
title: FortiClient plant access VPN cannot reach the gateway
category: VPN
doc_type: runbook
owner: Network Team
last_reviewed: 2026-08-30
applies_to: FortiClient 7.4 for Chennai plant systems and approved vendors, gateway plant-vpn.acme-demo.in
---

# FortiClient plant access VPN cannot reach the gateway

Plant engineering systems are reached through a separate FortiClient VPN. Staff laptops use GlobalProtect for everything else.

## Symptoms
- FortiClient stops at 40% and shows "Unable to establish the VPN connection. The VPN server may be unreachable."
- FortiClient reports "Credential or SSLVPN configuration is wrong".
- The connection works from the office but not from home.

## Resolution
1. Confirm you are using the plant profile: Remote Access > VPN name "ACME-PLANT", remote gateway plant-vpn.acme-demo.in, port 10443.
2. Disconnect GlobalProtect first; the two clients cannot be connected at the same time.
3. Sign in with your normal company account and approve the Authenticator prompt.
4. If the credential error appears, check in the Company Portal under "My access" that your plant access has not expired.
5. Try again from a phone hotspot to rule out a home router that blocks port 10443.

## Escalation criteria
Escalate to the Network Team when:
- The gateway is unreachable from two different networks.
- A vendor account needs renewing (vendor access is approved by the plant manager, not the service desk).
- The connection succeeds but plant systems on the 10.40.0.0/16 network do not respond.
