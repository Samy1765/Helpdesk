---
title: Scan to email or scan to folder does not arrive
category: Printer
doc_type: runbook
owner: Print Services
last_reviewed: 2026-07-10
applies_to: Multifunction devices (MFP) at Pune HQ, Bengaluru and Chennai
---

# Scan to email or scan to folder does not arrive

Scans are sent from scanner@acme-demo.in to your own mailbox only. Large colour scans can exceed the 20 MB limit and are dropped by the device without a warning.

## Symptoms
- The device says "Sent" but no email arrives.
- Scan to folder shows "Connection failed".
- Only some scans arrive, usually the short ones.

## Resolution
1. Tap your badge before scanning; Scan to Me sends to the email address linked to your badge.
2. Check the Junk Email folder and search Outlook for "scanner@acme-demo.in".
3. For multi-page documents, choose Black & White and 200 dpi, or split the scan into smaller parts.
4. For scan to folder, use the "My Scans" button, which saves to your OneDrive Scans folder; personal network folders are not supported.
5. Wait five minutes before scanning again; repeated retries can be queued and arrive together.

## Escalation criteria
Escalate to Print Services when:
- No scans from a specific device arrive for anyone (include the device name).
- Your badge is not recognised at the device.
