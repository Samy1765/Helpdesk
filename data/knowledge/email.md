---
title: Email and Outlook Troubleshooting Guide
category: Email
doc_type: runbook
---

# Email and Outlook Troubleshooting

## Outlook crashes or will not open
1. Close Outlook completely and check Task Manager that no OUTLOOK.EXE process remains.
2. Start Outlook in safe mode by holding Ctrl while clicking the Outlook icon, then confirm the prompt.
3. If safe mode works, open File > Options > Add-ins and disable recently installed COM add-ins, then restart normally.
4. Clear the Outlook application cache (the helpdesk agent can do this with your approval) and restart Outlook.
5. If Outlook still crashes, sign in to web mail to keep working while IT repairs the Office installation.

## Cannot send or receive email
1. Check the bottom status bar of Outlook: it must say "Connected" and not "Working Offline" (Send/Receive tab > Work Offline).
2. Look in the Outbox for a large message stuck there; move it to Drafts and remove large attachments (limit 25 MB).
3. Sign in to web mail. If web mail works, the issue is local to the Outlook client; restart Outlook.
4. If your mailbox is full you will see a quota warning; archive or delete old items with large attachments.

## Cannot access email at all
1. Sign in to web mail from a browser to check whether the account itself works.
2. If you are prompted for your password repeatedly, your password may have expired - reset it in the self-service portal.
3. Check the IT status page for an active email incident.

## Calendar or Teams meetings not syncing
1. In Outlook, right-click the calendar and choose Properties > Clear Offline Items, then Send/Receive.
2. Sign out of Teams and sign back in to refresh the calendar connection.
