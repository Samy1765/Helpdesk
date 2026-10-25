---
title: Unexpected MFA Prompts and Unusual Sign-in Alerts
category: Security
doc_type: runbook
last_reviewed: 2026-10-08
owner: Security Team
---

# Unexpected MFA Prompts and Unusual Sign-in Alerts

## Symptoms
- Your phone shows sign-in approval requests you did not start, sometimes many in a row.
- You receive an "Unusual sign-in activity" email or notification.
- An MFA prompt shows a location or app you do not recognise.

## What it means
Someone may already know your password and is hoping you approve a prompt by mistake or to make the notifications stop. Treat it as a security incident.

## Steps
1. Deny every prompt you did not start. If the app offers "Report", choose it.
2. Change your password immediately from a trusted device using the self-service portal.
3. Raise a Security ticket marked high priority with the time of the prompts and the location shown, if any.
4. Check your mailbox rules (Outlook, File, Rules and Alerts) for any rule you did not create, especially ones that forward or delete mail, and mention it in the ticket.
5. Do not approve a prompt "to see what happens", and do not share any code with someone who calls or messages you claiming to be IT.

## What the Security Team does
Signs out all your sessions, reviews recent sign-ins, and checks whether your password appears in known breach lists. They may ask you to register a new MFA method.

## Number matching
Our prompts ask you to type a two-digit number shown on the sign-in screen. If a prompt asks for a number and you are not looking at a sign-in screen, someone else is signing in. Deny it.
