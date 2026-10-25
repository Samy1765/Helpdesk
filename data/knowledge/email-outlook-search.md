---
title: Outlook Search Returns No or Incomplete Results
category: Email
doc_type: runbook
last_reviewed: 2026-08-20
owner: Email & Collaboration Team
---

# Outlook Search Returns No or Incomplete Results

## Symptoms
- Searching for a message you can see in the Inbox returns nothing.
- Outlook shows "Search results may be incomplete because items are still being indexed".
- Only recent mail appears in search results.

## Steps
1. Check the search scope at the top of the results: "Current Folder" only searches the folder you are in. Switch to "All Mailboxes".
2. Try the same search in Outlook on the web. If it works there, the problem is the local search index on your laptop, not your mailbox.
3. Leave Outlook open and the laptop plugged in for an hour; indexing pauses on battery power.
4. In Outlook, open File, Options, Search, Indexing Options, and check that Microsoft Outlook is listed under "Included locations".
5. Choose "Advanced" and then "Rebuild". Rebuilding can take several hours, and search is incomplete until it finishes.
6. Ask the helpdesk agent to clear the Outlook application cache (needs your approval) if results are still missing the next day.

## Good to know
Outlook keeps only the last 12 months of mail on the laptop by default. Older mail is found through "All Mailboxes" when you are online, or in Outlook on the web.

## When to escalate
Escalate if Outlook on the web also cannot find messages that are in the mailbox, which points to a server-side problem.
