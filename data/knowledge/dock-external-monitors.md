---
title: External monitors not detected through the docking station
category: Hardware
doc_type: runbook
owner: Hardware Support
last_reviewed: 2026-08-21
applies_to: Dell WD19S and Lenovo USB-C docks, 24-inch Dell P2423 monitors
---

# External monitors not detected through the docking station

Monitors that go black after the laptop wakes up are usually a dock that needs a power reset. Mixed cable types (one HDMI, one DisplayPort) are the next most common cause.

## Symptoms
- One or both external monitors show "No signal".
- The laptop screen works but Display settings shows only one display.
- The monitors flicker or the layout resets every morning.

## Resolution
1. Unplug the USB-C cable from the laptop, unplug the dock's power for 30 seconds, then reconnect power first and the laptop second.
2. Press Windows key + P and choose "Extend".
3. In Settings > System > Display, choose "Detect" under Multiple displays.
4. Check the input source on each monitor (button on the bottom edge) matches the cable used, HDMI or DisplayPort.
5. Install pending updates from Company Portal > Updates; dock firmware is delivered there.

## Escalation criteria
Escalate to Hardware Support when:
- A monitor shows "No signal" with a known good cable connected directly to the laptop.
- The dock does not power on or its light blinks amber.
- A monitor has lines, dead areas or a cracked panel.
