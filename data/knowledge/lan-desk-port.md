---
title: Desk network port or docking station gives no connection
category: Network
doc_type: runbook
owner: Network Team
last_reviewed: 2026-07-28
applies_to: Desk ports at Pune HQ floors 1-6, hot desks with Dell WD19S docks
---

# Desk network port or docking station gives no connection

Hot desks are wired through the docking station. A loose cable, a port disabled after a desk move, or a dock that needs a power reset are the usual causes.

## Symptoms
- Windows shows "Network cable unplugged" or an Ethernet icon with a red cross.
- The dock's network light is off.
- Wi-Fi works at the same desk.

## Resolution
1. Check both ends of the blue network cable: the wall port (labelled, for example, 3F-B-112) and the back of the dock.
2. Unplug the dock's power for 30 seconds, plug it back in, then reconnect the laptop.
3. Try the laptop's own Ethernet port, if it has one, with the same cable.
4. Move to a neighbouring desk to see whether the problem follows the laptop or stays with the desk.
5. Note the wall port label before raising a ticket; the Network Team needs it to check the switch.

## Escalation criteria
Escalate to the Network Team when:
- The wall port is dead with a known good cable and laptop. Include the port label.
- Several ports in the same bay stop working at once.
- Hardware Support handles faulty docks and cables; the agent routes those automatically.
