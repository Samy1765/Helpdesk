---
title: Browser Sign-in Loops and Web App Errors
category: Software
doc_type: runbook
last_reviewed: 2026-08-17
owner: Software Support
---

# Browser Sign-in Loops and Web App Errors

## Symptoms
- A company web app keeps returning to the sign-in page after you sign in.
- The page shows "Too many redirects", "Bad request - header too large" or a blank screen.
- The app works in another browser or for colleagues.

## Steps
1. Open the app in a private or incognito window. If it works there, the problem is stored data in your normal browser profile.
2. Clear cookies and cached files for the company sign-in site and for the affected app only (site settings, "Clear data"), rather than clearing everything.
3. Make sure you are signed in with your company account in the browser profile. Many sign-in loops happen when a personal account is active.
4. Turn off extensions one at a time, especially ad blockers, password managers and privacy tools.
5. Check the date, time and time zone on your laptop. Sign-in tokens are rejected if the clock is wrong.
6. Update the browser to the latest version and restart it.

## When to escalate
Raise a ticket for Software Support with the app name, the browser and a screenshot of the error if it also fails in a private window. If several people report the same app, check the IT status page first.
