---
title: Print jobs stay in the queue and never print
category: Printer
doc_type: runbook
owner: Print Services
last_reviewed: 2026-09-15
applies_to: Acme Secure Print queue and floor printers such as PUN-3F-MFP01
---

# Print jobs stay in the queue and never print

All office printing goes through the Acme Secure Print queue: jobs wait on the server until you tap your badge at any printer. A job that never appears at the printer is usually stuck on the laptop, in the local print spooler.

## Symptoms
- The job shows "Error - Printing" or "Spooling" in the print queue window for more than two minutes.
- Nothing appears when you tap your badge at the printer.
- New jobs queue up behind the first one.

## Resolution
1. Open Settings > Bluetooth & devices > Printers & scanners > Acme Secure Print > Open print queue, and cancel the stuck job.
2. Restart the print spooler on your laptop. The helpdesk agent can do this for you once you approve it; queued jobs on the laptop are cancelled.
3. Print a one-page test from Notepad to Acme Secure Print.
4. Tap your badge at the printer, choose Print Release and select the job.
5. If the job is a large PDF, print it as an image (Acrobat: Print > Advanced > Print as image).

## Escalation criteria
Escalate to Print Services when:
- Jobs reach the release list but the printer shows an error code (include the code and printer name).
- Nobody on the floor can release jobs (possible print server or badge reader issue).
- The test page from Notepad also stays stuck after the spooler restart.
