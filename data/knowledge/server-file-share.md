---
title: Network Drive Missing or Access Denied on a File Share
category: Server
doc_type: runbook
last_reviewed: 2026-08-15
owner: Server Operations
---

# Network Drive Missing or Access Denied on a File Share

## Mapped drive is missing (for example the S: drive)
1. Connect to the VPN if you are working remotely. Drives are mapped at sign-in and only when the file server can be reached.
2. Sign out of Windows and sign in again while connected, so the drive mapping runs again.
3. Open File Explorer and type the share path (for example `\\files\finance`) in the address bar to check whether the share itself is reachable.

## "Access denied" or "You don't have permission"
1. Folder access is granted by the folder owner, normally a team lead. Ask them to confirm you are in the right group.
2. After access is granted, sign out and in again; group membership only updates at sign-in.
3. If you could open the folder yesterday and cannot today, check with colleagues: if nobody can, it is a server problem, not your permissions.

## Accidentally deleted or overwritten a file
1. Right-click the folder, choose "Properties", then "Previous Versions" and restore a copy. Snapshots are taken every four hours and kept for 30 days.
2. If no previous versions are listed, raise a ticket with the full path and the time the file was last correct.

## Moving to SharePoint
Most team shares are moving to SharePoint during 2026. If your team has already moved, the old drive is read-only.

## When to escalate
Raise a ticket for Server Operations if the share path is unreachable for more than one person, or if Previous Versions is empty for a folder you need restored.
