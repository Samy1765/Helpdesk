---
title: Office Wi-Fi shows connected but pages do not load
category: Network
doc_type: runbook
owner: Network Team
last_reviewed: 2026-10-02
applies_to: SSID ACME-CORP at Pune HQ, Bengaluru office and Chennai plant
---

# Office Wi-Fi shows connected but pages do not load

ACME-CORP assigns an address only after the laptop's device certificate is accepted. A laptop that joined the guest network, or whose certificate expired, can show "No internet, secured".

## Symptoms
- The Wi-Fi icon shows a globe or "No internet, secured".
- Browsers time out on every site, including the intranet.
- Colleagues on the same floor are working normally.

## Resolution
1. Make sure you are on ACME-CORP and not ACME-GUEST or a phone hotspot with a similar name.
2. Turn Wi-Fi off and on again from the taskbar, then wait 30 seconds.
3. Forget the ACME-CORP network (Settings > Network & internet > Wi-Fi > Manage known networks) and join it again; the certificate is selected automatically.
4. Flush the DNS cache. The helpdesk agent can do this with your approval.
5. Plug into a desk network port if one is free, to confirm whether the problem is Wi-Fi only.

## Escalation criteria
Escalate to the Network Team when:
- The laptop gets an address starting with 169.254 (no address from the network).
- Several people in the same area lose access at the same time; include the floor and wing.
- The wired port works but ACME-CORP still fails after the steps above.
