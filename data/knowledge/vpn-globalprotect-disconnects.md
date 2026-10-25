---
title: GlobalProtect connects, then drops every few minutes
category: VPN
doc_type: runbook
owner: Network Team
last_reviewed: 2026-09-22
applies_to: GlobalProtect 6.2 on home broadband, hotel and mobile networks
---

# GlobalProtect connects, then drops every few minutes

Repeated drops are almost always caused by an unstable local network, a second VPN or proxy tool, or a stale DNS cache on the laptop.

## Symptoms
- The tray icon switches between Connected and Reconnecting every few minutes.
- Teams calls freeze and file shares disconnect while the VPN shows Connected.
- The GlobalProtect log shows "tunnel keep-alive timeout".

## Resolution
1. Move closer to the router or use a network cable; a Wi-Fi signal below two bars causes keep-alive timeouts.
2. Close any other VPN, proxy or "secure browsing" app. Only one VPN can run at a time.
3. Restart the GlobalProtect service. The helpdesk agent can do this for you once you approve it.
4. Flush the DNS cache. The helpdesk agent can also do this with your approval.
5. Reconnect and leave the agent open for ten minutes to confirm the tunnel stays up.
6. On a hotel or airport network, switch to a phone hotspot; some guest networks reset long connections.

## Escalation criteria
Escalate to the Network Team when:
- Drops continue on a wired connection after the service restart.
- The laptop drops every 30 or 60 minutes exactly (likely a gateway timeout setting).
- Several users at the same site report drops at the same time.
