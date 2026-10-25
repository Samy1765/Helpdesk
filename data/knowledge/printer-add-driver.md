---
title: Adding a Printer and Fixing Driver Problems
category: Printer
doc_type: runbook
last_reviewed: 2026-07-22
owner: Print Services
---

# Adding a Printer and Fixing Driver Problems

## Adding a printer
Most people only need the "FollowMe" secure queue, which is installed on every company laptop. To add a specific printer, for example a plotter or a label printer:

1. Open Software Center and search for "Printer".
2. Select the printer by its location name (for example "PUNE-3F-PLOTTER") and choose "Install".
3. Print a test page from the printer properties.

## Printing produces garbled text or blank pages
1. Remove the printer, then reinstall it from Software Center so the current driver is used.
2. Try printing the document as a PDF first and print the PDF; some old documents use unusual fonts.
3. Ask the helpdesk agent to restart the print spooler on your laptop (needs your approval).

## "Driver unavailable" in printer settings
This happens after major Windows updates. Remove the printer and reinstall it from Software Center. Do not download drivers from the manufacturer's website; laptops block unsigned drivers.

## Home printers
Personal printers can be used for non-confidential documents only. You can add them through Windows Settings; IT does not support them.

## When to escalate
Raise a ticket for Print Services if the printer is not listed in Software Center, or if reinstalling does not fix garbled output.
