---
title: Wired Connection Shows "No Internet" or a 169.254 Address
category: Network
doc_type: runbook
last_reviewed: 2026-07-30
owner: Network Team
---

# Wired Connection Shows "No Internet" or a 169.254 Address

## Symptoms
- The network icon shows a globe with a red cross or "Unidentified network".
- Network details show an IPv4 address starting with 169.254, meaning the laptop never received an address.
- Windows reports "IP address conflict".

## Steps
1. Check that the cable clicks into both the laptop (or dock) and the wall port, and that the port light is on.
2. Try a different wall port or a different cable; floor ports are sometimes disabled when desks move.
3. Unplug the dock from power for ten seconds and reconnect it; docks often hold a stale network state.
4. Ask the helpdesk agent to flush the DNS cache (needs your approval). The agent can also check whether internal services respond from the network.
5. Restart the laptop with the cable connected.

## IP address conflict
Another device is using the same address, usually a personal device or a printer set up with a fixed address. Disconnect, wait one minute and reconnect so a new address is issued, then report the desk number so the Network Team can find the other device.

## When to escalate
Escalate to the Network Team with your desk or port number if a second port and cable also fail, or if several desks in the same area lose their connection.
