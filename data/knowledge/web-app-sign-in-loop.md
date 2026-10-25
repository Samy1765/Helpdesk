---
title: Internal web application keeps returning to the sign-in page
category: Software
doc_type: runbook
owner: Software Support
last_reviewed: 2026-08-05
applies_to: Acme ERP (web), Acme Connect intranet and HR portal in Edge or Chrome
---

# Internal web application keeps returning to the sign-in page

Sign-in loops come from an old session cookie that no longer matches your single sign-on session, or from a browser profile signed in to a personal account.

## Symptoms
- After signing in, the page reloads and asks you to sign in again.
- The application shows "AADSTS50058" or "Your session has expired" straight after sign-in.
- The same application works in a private browser window.

## Resolution
1. Open a private (InPrivate or Incognito) window and try the application there to confirm it is a browser problem.
2. In Edge or Chrome, clear cookies for the site only: click the lock icon in the address bar > Cookies and site data > Manage > remove entries for acme-demo.in.
3. Make sure the browser profile is your work profile (top-right picture shows your company account).
4. Close every browser window, then open the application again from the intranet link.
5. Check the date and time on the laptop are set automatically.

## Escalation criteria
Escalate to Software Support when:
- The loop also happens in a private window.
- The application shows an error code that starts with AADSTS other than 50058; include the full code.
Escalate to Server Operations when the application is down for everyone.
