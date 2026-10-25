---
title: VPN shows connected but internal sites and file shares do not open
category: VPN
doc_type: runbook
owner: Network Team
last_reviewed: 2026-09-05
applies_to: GlobalProtect 6.2, intranet Acme Connect, file shares on fs01.acme-demo.in
---

# VPN shows connected but internal sites and file shares do not open

When the tunnel is up but names do not resolve, the laptop is usually still using the home router for DNS, or an old mapped drive points at a retired server.

## Symptoms
- GlobalProtect shows Connected, but https://connect.acme-demo.in says "This site can't be reached".
- Mapped drives show a red cross in File Explorer.
- Public websites work normally.

## Resolution
1. Disconnect GlobalProtect, wait ten seconds and connect again so the company DNS settings are pushed again.
2. Flush the DNS cache. The helpdesk agent can do this for you with your approval.
3. Open the intranet by its full name, https://connect.acme-demo.in, rather than a bookmark with a short name.
4. In File Explorer, right-click any mapped drive that points to fs-old or nas01 and choose Disconnect. Current shares live on fs01.acme-demo.in.
5. Restart the laptop if drives still show a red cross after reconnecting.

## Escalation criteria
Escalate to the Network Team when:
- Internal names still do not resolve after a reconnect and a restart.
- Only one internal site fails while others work (the application owner may need to check it).
