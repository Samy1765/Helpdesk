# Screenshots: before and after the redesign

Captured with headless Microsoft Edge at **1366×768** and **1920×1080** (Asia/Kolkata time zone), signed in as the
demo accounts. "Before" is commit `8126b23` with its original seed data; "after" is this branch with the demo company
seed (`SEED_DEMO_DATA=true`). Every page was also checked with axe-core (WCAG 2.0/2.1 A and AA rules), a keyboard
walk of the first 25 tab stops (each must show a focus indicator), a horizontal-overflow check, a console-error check
and a Content-Security-Policy violation listener.

Full-size images for both resolutions are in [before/](before/) and [after/](after/), named `<page>-<width>x<height>.png`.

## Accessibility and consistency (1366×768; 1920×1080 gives the same counts)

| Page | axe violations before | after | distinct font sizes before | after |
|---|---|---|---|---|
| Sign in | 1 (color-contrast) | 0 | 6 | 4 |
| Home | 3 (color-contrast) | 0 | 9 | 4 |
| Get help (chat) | 1 (color-contrast) | 0 | 8 | 3 |
| Tickets | 2 (select-name) | 0 | 8 | 3 |
| Ticket detail | 9 (color-contrast, scrollable-region-focusable) | 0 | 8 | 3 |
| Incidents | 8 (color-contrast, link-in-text-block) | 0 | 7 | 4 |
| Knowledge base | 1 (select-name) | 0 | 6 | 4 |
| IT support queue | 16 (color-contrast, link-in-text-block, select-name) | 0 | 7 | 4 |
| Admin analytics | 81 (label, select-name) | 0 | 8 | 4 |
| Profile | 1 (color-contrast) | 0 | 8 | 4 |
| **Total** | **123** | **0** | | |

After: no horizontal scrolling at either size, no console errors, no CSP violations under the strict policy
(`script-src 'self'; style-src 'self'; font-src 'self'`), and every keyboard focus stop shows a visible outline.
All text uses the 12 / 14 / 16 / 20 / 24 px scale.

## Side by side (1366×768)

| Page | Before | After |
|---|---|---|
| Sign in | ![before login 1366](before/login-1366x768.png) | ![after login 1366](after/login-1366x768.png) |
| Home | ![before dashboard 1366](before/dashboard-1366x768.png) | ![after dashboard 1366](after/dashboard-1366x768.png) |
| Get help (chat) | ![before chat 1366](before/chat-1366x768.png) | ![after chat 1366](after/chat-1366x768.png) |
| Tickets | ![before tickets 1366](before/tickets-1366x768.png) | ![after tickets 1366](after/tickets-1366x768.png) |
| Ticket detail | ![before ticket-detail 1366](before/ticket-detail-1366x768.png) | ![after ticket-detail 1366](after/ticket-detail-1366x768.png) |
| Incidents | ![before incidents 1366](before/incidents-1366x768.png) | ![after incidents 1366](after/incidents-1366x768.png) |
| Knowledge base | ![before knowledge-base 1366](before/knowledge-base-1366x768.png) | ![after knowledge-base 1366](after/knowledge-base-1366x768.png) |
| IT support queue | ![before it-support 1366](before/it-support-1366x768.png) | ![after it-support 1366](after/it-support-1366x768.png) |
| Admin analytics | ![before admin-analytics 1366](before/admin-analytics-1366x768.png) | ![after admin-analytics 1366](after/admin-analytics-1366x768.png) |
| Profile | ![before profile 1366](before/profile-1366x768.png) | ![after profile 1366](after/profile-1366x768.png) |
