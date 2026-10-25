---
title: Windows or Company Portal updates keep failing
category: Software
doc_type: runbook
owner: Software Support
last_reviewed: 2026-09-30
applies_to: Windows 11 23H2/24H2 laptops managed by Intune
---

# Windows or Company Portal updates keep failing

Laptops must install monthly security updates within 14 days, otherwise they are marked non-compliant and lose access to email and Wi-Fi. Most failures are low disk space or a laptop that has not restarted for weeks.

## Symptoms
- Settings > Windows Update shows "Install error - 0x800f0922" or a similar code.
- The Company Portal shows the device as "Not compliant" with "Update required".
- The same update tries to install every night.

## Resolution
1. Restart the laptop (Start > Power > Update and restart if offered), not just close the lid.
2. Check free disk space in File Explorer; at least 20 GB is needed. Empty the Recycle Bin and clear the Downloads folder.
3. Connect to the office network or VPN, then open Settings > Windows Update > Check for updates.
4. Keep the laptop on charge and connected during the update; it may restart twice.
5. Open the Company Portal and choose "Check status" to refresh compliance after the update.

## Escalation criteria
Escalate to Software Support when:
- The same update fails three times with the same error code.
- The device stays "Not compliant" for more than a day after updates succeed.
- Disk space cannot be freed because the drive is full of work data (Hardware Support can provide a larger drive).
