---
title: VPN Client on macOS Will Not Start or Connect
category: VPN
doc_type: runbook
last_reviewed: 2026-09-02
owner: Network Team
---

# VPN Client on macOS Will Not Start or Connect

## Symptoms
- After a macOS upgrade the VPN icon is missing or the client says "VPN service not available".
- macOS shows "System Extension Blocked".

## Steps
1. Open System Settings, then Privacy & Security, scroll down and click "Allow" next to the message about the VPN client's system software.
2. In System Settings, open General, then Login Items & Extensions, then Network Extensions, and make sure the VPN client is switched on.
3. Quit the client from the menu bar and open it again from Applications.
4. If the client still cannot start, install the current version from Self Service; older versions are not supported on the latest macOS release.
5. Restart the Mac after installing and connect again.

## Notes
- Approving the extension needs an administrator password only on personally managed Macs; company Macs approve it automatically after the next device check-in, which can take up to 30 minutes.
- Do not install VPN clients downloaded from the internet. Only the Self Service version is configured for the company gateway.

## When to escalate
Escalate to the Network Team if the extension is not listed, or if Self Service reports the installation failed.
