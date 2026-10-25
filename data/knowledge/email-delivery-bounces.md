---
title: Emails bounce, sit in the Outbox or never reach the recipient
category: Email
doc_type: runbook
owner: Email & Collaboration Team
last_reviewed: 2026-09-29
applies_to: Exchange Online mailboxes; outbound mail via mail.acme-demo.in
---

# Emails bounce, sit in the Outbox or never reach the recipient

Most delivery problems are visible in the bounce message (non-delivery report). The code near the top tells you which of the cases below applies.

## Symptoms
- You receive "Undeliverable" or "Delivery has failed" with a code such as 550 5.1.1 or 552 5.3.4.
- A message stays in the Outbox and is never sent.
- An external partner says your email never arrived, but there is no bounce.

## Resolution
1. Read the bounce: 5.1.1 means the address does not exist; check the spelling or ask the recipient for the correct address.
2. Code 5.3.4 or "message too large" means the attachment is over 25 MB; share the file from OneDrive with "Specific people" instead.
3. For a message stuck in the Outbox, check that Outlook says "Connected" in the status bar, then move the message to Drafts, remove large attachments and send it again.
4. If a partner says nothing arrived, ask them to check their junk folder and quarantine, and send a test message without attachments.
5. If you expected an external email that never arrived, check the quarantine digest email sent to you each morning and release it if it is legitimate.

## Escalation criteria
Escalate to the Email & Collaboration Team when:
- Several recipients at one external company bounce your mail with 5.7.x codes (possible block list issue).
- Mail to everyone is delayed by more than 30 minutes.
Report to the Security Team, not the mail team, when a bounce arrives for a message you did not send.
