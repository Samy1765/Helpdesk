---
title: Access denied to a team folder on the file server
category: Server
doc_type: guide
owner: Server Operations
last_reviewed: 2026-07-06
applies_to: Team shares on fs01.acme-demo.in and SharePoint team sites
---

# Access denied to a team folder on the file server

Team folders are protected by access groups owned by each department. IT adds you to a group only when the folder's data owner approves, so the request goes to them first.

## Symptoms
- File Explorer shows "You don't have permission to access this folder".
- You can see the folder but cannot save changes (read-only access).
- A folder disappeared after you moved to a new team.

## Resolution
1. Check the full path of the folder (for example, \\fs01.acme-demo.in\finance\ap-invoices) and copy it into the request.
2. In the Company Portal, open "Request access" > "File share access", paste the path and choose read or edit.
3. The request goes to the folder's data owner for approval; you get an email when it is granted.
4. After approval, sign out of Windows and back in so the new group membership takes effect.
5. For SharePoint team sites, use the "Request access" button on the site instead.

## Escalation criteria
Escalate to Server Operations when:
- Access was approved but is still denied after signing out and in.
- A whole team loses access to a folder at the same time.
- A folder or files have disappeared (they can be restored from the previous 30 days of snapshots).
