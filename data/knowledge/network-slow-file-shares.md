---
title: Network is slow when opening files or loading internal apps
category: Network
doc_type: guide
owner: Network Team
last_reviewed: 2026-09-10
applies_to: Offices and VPN users; shares on fs01.acme-demo.in
---

# Network is slow when opening files or loading internal apps

Slowness is often local (weak Wi-Fi, a large OneDrive sync, dozens of browser tabs) rather than the company network. These checks separate the two.

## Symptoms
- Opening an Excel file from the file share takes more than a minute.
- Internal web apps load slowly while public sites are fine, or the reverse.
- Video calls report "Your network connection is unstable".

## Resolution
1. Pause OneDrive sync from its taskbar icon for two hours and see whether things improve.
2. Close unused browser tabs and video calls, then open the same file again.
3. Move closer to an access point or plug into a desk port, and compare the speed.
4. On VPN, open large files from SharePoint rather than the file share; SharePoint does not travel through the tunnel.
5. Note the time, location and what was slow; a pattern helps the Network Team find congestion.

## Escalation criteria
Escalate to the Network Team when:
- Slowness affects a whole floor, team or site at the same time.
- A wired connection is as slow as Wi-Fi for more than 30 minutes.
- Calls drop for several people at once (possible internet link saturation).
