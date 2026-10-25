---
title: Laptop cannot join the ACME-CORP Wi-Fi network
category: Network
doc_type: runbook
owner: Network Team
last_reviewed: 2026-08-14
applies_to: Company-managed Windows and macOS laptops; personal devices use ACME-GUEST
---

# Laptop cannot join the ACME-CORP Wi-Fi network

ACME-CORP uses certificate-based sign-in (802.1X). Only company-managed laptops receive the certificate; phones and personal laptops use ACME-GUEST.

## Symptoms
- Windows shows "Can't connect to this network" when choosing ACME-CORP.
- The laptop asks for a username and password for ACME-CORP (it should never ask).
- A new laptop works at home but not in the office.

## Resolution
1. Check that the laptop is company-managed: the Company Portal app must show the device as "Compliant".
2. Connect to ACME-GUEST or a wired port, open the Company Portal, choose Sync and wait five minutes for the Wi-Fi certificate.
3. Restart the laptop and select ACME-CORP again. If a username prompt appears, cancel it rather than typing anything.
4. If the Company Portal shows "Not compliant", follow the actions it lists, usually a pending Windows update or a BitLocker check.

## Escalation criteria
Escalate to the Network Team when:
- The device is compliant but no Wi-Fi certificate arrives after a sync and a restart.
- A new hire's laptop was never enrolled (the Service Desk enrols it first).
