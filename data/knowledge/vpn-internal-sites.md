---
title: VPN Connected but Internal Sites Do Not Open
category: VPN
doc_type: runbook
last_reviewed: 2026-09-18
owner: Network Team
---

# VPN Connected but Internal Sites Do Not Open

## Symptoms
- The VPN client shows "Connected", yet the intranet, HR portal or file shares time out.
- Public websites work normally.
- Internal names such as `intranet.corp` return "server not found" while their IP addresses respond.

## Why it happens
Internal names are resolved by the company DNS servers, which are only handed out once the tunnel is up. If the laptop keeps using the home router or a public DNS service, internal names never resolve. A second VPN or a browser proxy extension can also capture the traffic before it reaches the tunnel.

## Steps
1. Disconnect and reconnect the VPN once, then wait 20 seconds before opening an internal page.
2. Turn off any personal VPN, "secure DNS" setting or proxy extension in the browser.
3. Ask the helpdesk agent to flush the DNS cache on your device (needs your approval), then try the page again.
4. Try the page in a private browser window to rule out a cached redirect.
5. If only one internal site fails, check the IT status page; the site itself may be down rather than your VPN.

## When to escalate
Escalate to the Network Team if internal names still fail after a DNS flush, or if several colleagues on the VPN report the same site at the same time (the agent will group these reports into one incident).
