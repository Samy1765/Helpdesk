---
title: VPN Troubleshooting Runbook (Cisco AnyConnect)
category: VPN
doc_type: runbook
---

# VPN Troubleshooting Runbook

## VPN fails at login or after entering the MFA code
Most failures right after the MFA prompt come from a stale authentication session cached by the VPN client.

1. Disconnect the VPN client and fully quit it from the system tray (right-click the icon, choose Quit).
2. Open the company SSO portal in your browser and sign out, then sign back in to refresh your SSO session.
3. Make sure your device clock is set automatically; MFA codes fail when the clock is more than 30 seconds off.
4. Reopen the VPN client, connect to the default gateway and approve the MFA prompt within 60 seconds.
5. If the client shows SEC_AUTH_403, your VPN entitlement has expired - request VPN access renewal in the self-service portal.

## VPN connects and then disconnects
Frequent drops are usually caused by an unstable home network or a stale DNS cache.

1. Switch from Wi-Fi to a wired connection, or move closer to your router, and try again.
2. Pause any other VPN, proxy or "secure browsing" tools; two VPNs cannot run at the same time.
3. Restart the VPN client service (the helpdesk agent can do this for you with your approval).
4. Flush the DNS cache on your device (the helpdesk agent can do this with your approval).
5. Reconnect and keep the client open for five minutes to confirm the session stays up.

## Cannot reach the VPN gateway at all
1. Confirm you have general internet access by opening any public website.
2. Hotel, airport and guest networks often block VPN ports; try a mobile hotspot.
3. Check the IT status page for an active VPN incident before troubleshooting further.
