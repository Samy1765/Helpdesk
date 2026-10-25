"""
Precision AI - Demo organisation: a quarter of helpdesk history for presentations.

Called by `python -m app.database.seed` on a new database (the Docker image runs it when
SEED_DEMO_DATA=true). Everything is synthetic: invented people with @example.com addresses and
invented tickets. Generation is deterministic (random.Random(42)), so every fresh demo database
looks the same.

The rows are written directly (with past timestamps) rather than replayed through the agent,
because replaying ~350 tickets would take minutes and could not back-date them. Tickets that the
assistant resolves stay on levels L1-L3 (articles and verified fixes), which need no language
model, so the analytics remain consistent with a demo that runs without LLM keys.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import select, update
from sqlalchemy.orm.attributes import set_committed_value

from app.core.config import get_settings
from app.core.security import hash_password
from app.database.session import utcnow
from app.models import (
    AgentAction, AgentRun, Incident, Ticket, TicketAssignment, TicketCategory, TicketEscalation, TicketEvent,
    TicketFeedback, TicketMessage, TicketSolution, TicketStatus, TroubleshootingStep, User,
)
from app.models.knowledge import KnowledgeDocument
from app.tools.registry import get_tool

DEMO_PASSWORD = "Demo@12345"
MARKER_USERNAME = "aarav.kulkarni"  # first generated employee; its presence means the demo data exists

FIRST = ["Aarav", "Ananya", "Rohan", "Isha", "Vikram", "Neha", "Arjun", "Pooja", "Kabir", "Meera", "Siddharth",
         "Tanvi", "Aditya", "Riya", "Karan", "Sneha", "Nikhil", "Divya", "Rahul", "Shreya", "Omkar", "Aditi",
         "Varun", "Kavya", "Harsh", "Nisha", "Yash", "Priyanka", "Manish", "Sanya", "Daniel", "Fatima",
         "Lucas", "Mei", "Samuel", "Leila", "Imran", "Grace", "Tejas", "Ira", "Kunal", "Anjali", "Pranav",
         "Rutuja", "Sahil"]
LAST = ["Kulkarni", "Deshpande", "Joshi", "Patil", "Iyer", "Menon", "Shah", "Gupta", "Rao", "Nair", "Bhosale",
        "Chavan", "Pawar", "Reddy", "Mehta", "Kapoor", "Sinha", "Banerjee", "Fernandes", "Dsouza", "Khan",
        "Thomas", "Pillai", "Sawant", "Gokhale"]
LOCATIONS = ["Pune HQ", "Pune HQ", "Pune HQ", "Mumbai office", "Bengaluru office", "Remote"]
TITLES = {
    "BU_FINANCE": ["Accountant", "Financial Analyst", "Accounts Payable Executive", "Payroll Executive", "Finance Manager"],
    "BU_ENGINEERING": ["Software Engineer", "Senior Software Engineer", "QA Engineer", "DevOps Engineer", "Engineering Manager"],
    "BU_DESIGN": ["Product Designer", "UX Researcher", "Visual Designer"],
    "BU_SALES": ["Account Executive", "Sales Manager", "Inside Sales Representative", "Pre-sales Consultant"],
    "BU_HR": ["HR Executive", "Recruiter", "HR Business Partner"],
}
BUSINESS_UNITS = ["BU_ENGINEERING"] * 4 + ["BU_SALES"] * 3 + ["BU_FINANCE"] * 3 + ["BU_DESIGN"] * 2 + ["BU_HR"] * 2

# (username, full name, role, team code, job title)
EXTRA_STAFF = [
    ("nikhil.joshi", "Nikhil Joshi", "it_support", "NETWORK", "Network Engineer"),
    ("sneha.kulkarni", "Sneha Kulkarni", "it_support", "SERVICE_DESK", "Service Desk Analyst"),
    ("rutuja.patil", "Rutuja Patil", "admin", "SERVICE_DESK", "IT Service Manager"),
]

CATEGORY_WEIGHTS = {"Password": 18, "Email": 15, "VPN": 13, "Software": 12, "Hardware": 11, "Network": 9,
                    "Printer": 9, "Security": 5, "Database": 4, "Server": 4}
WEEKDAY_WEIGHTS = [1.4, 1.2, 1.1, 1.0, 0.9, 0.2, 0.12]  # Monday first
# Hours in UTC, weighted towards Indian office hours (09:00-18:30 IST = 03:30-13:00 UTC)
HOUR_WEIGHTS = {3: 2, 4: 6, 5: 7, 6: 6, 7: 4, 8: 5, 9: 6, 10: 5, 11: 4, 12: 2, 13: 1, 14: 0.5, 16: 0.3}
STAFF_HOURS = {"critical": (0.4, 1.5), "high": (1, 5), "medium": (1.5, 10), "low": (3, 30)}


@dataclass
class Template:
    category: str
    intent: str
    titles: list[str]
    descriptions: list[str]
    fix_title: str
    fix: str
    steps: list[str]
    root_cause: str
    priorities: dict[str, int]
    ai_share: float          # share of cases the assistant resolves once a verified fix exists
    action: Optional[str] = None
    entities: dict = field(default_factory=dict)


T = Template
TEMPLATES: list[Template] = [
    # ---------------- Password ----------------
    T("Password", "account_locked", ["Account locked after password change", "Locked out of my laptop", "Account keeps getting locked"],
      ["I changed my password on Friday and today my account is locked every few minutes.",
       "Windows says my account is locked. I only tried my password twice.",
       "My account locks again a short while after it is unlocked. Phone mail is still on the old password I think."],
      "Unlock account and update saved passwords", "Unlocked the account and removed the old password from the phone mail app and saved Wi-Fi profile.",
      ["Unlock the account (with your approval)", "Update the password in the phone mail app", "Forget and rejoin saved Wi-Fi networks", "Sign out and back in on the laptop"],
      "Old password cached on a phone and a saved Wi-Fi profile.", {"medium": 6, "high": 3, "low": 1}, 0.7, "unlock_account"),
    T("Password", "password_reset", ["Forgot my password", "Password expired while on leave", "Need a password reset"],
      ["Came back from leave and my password has expired. The reset page asks for a code I do not get.",
       "I forgot my password and the self-service page says I am not registered.",
       "Password expired this morning and I cannot get past the sign-in screen."],
      "Reset password by verified reset link", "Sent a reset link to the registered personal email and confirmed the new password works on the laptop over VPN.",
      ["Request a reset link to your registered personal email", "Choose a new password of at least 12 characters", "Sign in to the laptop while connected to the VPN"],
      "Self-service verification methods not registered.", {"medium": 7, "low": 2, "high": 1}, 0.65, "send_password_reset_link"),
    T("Password", "mfa_issue", ["New phone, MFA not working", "Authenticator codes rejected", "Not receiving MFA prompts"],
      ["I changed my phone and the authenticator app has no account now.",
       "The six digit codes from the authenticator are always rejected.",
       "MFA approval notifications stopped arriving on my phone."],
      "Re-register the authenticator app", "Set the phone clock to automatic, removed the old device and registered the authenticator again from the security info page.",
      ["Set the phone date and time to automatic", "Open the security info page on the laptop", "Add the authenticator app and scan the QR code", "Remove the old phone from the list"],
      "Authenticator registered to the previous phone.", {"medium": 6, "high": 2, "low": 2}, 0.5),
    # ---------------- Email ----------------
    T("Email", "outlook_crash", ["Outlook closes on start", "Outlook crashes when opening attachments", "Outlook not responding"],
      ["Outlook opens for two seconds and then closes. Restarted twice already.",
       "Outlook crashes every time I open a PDF attachment.",
       "Outlook freezes at 'Loading profile' since this morning."],
      "Repair Outlook profile and clear cache", "Cleared the Outlook cache, disabled a faulty add-in and repaired the Office installation.",
      ["Close Outlook fully", "Clear the Outlook application cache (with your approval)", "Start Outlook in safe mode and disable add-ins", "Run Office Quick Repair"],
      "Faulty third-party add-in and corrupted cache.", {"medium": 7, "high": 2, "low": 1}, 0.6, "clear_application_cache"),
    T("Email", "email_send_receive", ["Emails stuck in Outbox", "Not receiving external emails", "Mailbox full warning"],
      ["My emails stay in the Outbox and are never sent.",
       "Customers say their emails to me bounce back.",
       "Outlook says my mailbox is almost full and I cannot send."],
      "Free mailbox space and archive old mail", "Moved mail older than a year to the online archive and applied the archive policy to the Inbox.",
      ["Check folder sizes", "Move old mail to the Online Archive", "Empty Deleted Items", "Apply the one-year archive policy"],
      "Mailbox over the sending limit.", {"medium": 6, "high": 2, "low": 2}, 0.55),
    T("Email", "calendar_sync", ["Teams meetings missing from calendar", "Shared calendar not updating", "Calendar invites not showing"],
      ["Meetings accepted on my phone do not show in Outlook on the laptop.",
       "The team's shared calendar has not updated since yesterday.",
       "Teams meeting invites never appear in my calendar."],
      "Re-sync calendar and shared calendars", "Removed and re-added the shared calendar and reset the Outlook cached mode for the calendar folder.",
      ["Remove the shared calendar from Outlook", "Add it again from the address book", "Restart Outlook and wait for sync"],
      "Stale cached calendar folder.", {"low": 5, "medium": 5}, 0.5),
    # ---------------- VPN ----------------
    T("VPN", "vpn_mfa_failure", ["VPN fails after MFA", "VPN login loop", "VPN asks for MFA again and again"],
      ["The VPN client accepts my password and then fails right after I approve the MFA prompt.",
       "VPN keeps asking me to approve sign-in and never connects. Working from home today.",
       "Every time I connect the VPN it goes back to the login screen after the MFA step."],
      "Refresh SSO session and restart VPN client", "Quit the VPN client, refreshed the SSO session in the browser, restarted the VPN client service and reconnected.",
      ["Quit the VPN client from the system tray", "Sign out of the SSO portal and sign in again", "Restart the VPN client service (with your approval)", "Reconnect and approve MFA within 60 seconds"],
      "Stale authentication token in the VPN client.", {"medium": 7, "high": 3}, 0.75, "restart_vpn_client_service"),
    T("VPN", "vpn_connection_failure", ["VPN blocked: device not compliant", "VPN cannot reach gateway", "Intranet not loading on VPN"],
      ["The VPN says my device is not compliant and will not connect.",
       "From the hotel the VPN client says it cannot reach the gateway.",
       "VPN is connected but intranet pages do not load. Public websites are fine."],
      "Fix VPN compliance and DNS", "Installed pending updates, refreshed antivirus definitions and flushed the DNS cache before reconnecting.",
      ["Install pending updates and restart", "Update antivirus definitions", "Flush the DNS cache (with your approval)", "Reconnect the VPN"],
      "Pending OS update failed the compliance check.", {"medium": 6, "high": 3, "low": 1}, 0.6, "flush_dns_cache"),
    # ---------------- Software ----------------
    T("Software", "software_install_request", ["Need Power BI Desktop", "Request: Visual Studio Code", "Install request for Tableau Reader"],
      ["I need Power BI Desktop for the monthly sales report.",
       "Please install Visual Studio Code, it is not in Software Center.",
       "Client sent dashboards that need Tableau Reader."],
      "Install from Software Center", "Published the package to the user's Software Center collection; user installed it.",
      ["Open Software Center", "Search for the application", "Choose Install and wait until it shows Installed"],
      "Application not assigned to the user's collection.", {"low": 8, "medium": 2}, 0.4),
    T("Software", "license_activation", ["Office says unlicensed product", "Adobe asks to sign in again", "Licence expired message in Excel"],
      ["Word shows a red bar saying unlicensed product.",
       "Adobe Acrobat keeps asking me to sign in and then says no licence.",
       "Excel opened read-only with a licence expired message."],
      "Re-activate with company account", "Signed out the personal account, cleared the Office cache and signed in with the company account.",
      ["Check the signed-in account under File > Account", "Sign out of any personal account", "Clear the application cache (with your approval)", "Sign in with the company account"],
      "Personal account signed in to Office.", {"medium": 6, "low": 3, "high": 1}, 0.6, "clear_application_cache"),
    T("Software", "software_crash", ["ERP client crashes on export", "Browser shows too many redirects", "Teams keeps crashing"],
      ["The ERP client closes whenever I export the ledger to Excel.",
       "The HR portal shows too many redirects in Chrome.",
       "Teams crashes during screen sharing."],
      "Clear app data and update client", "Cleared the application cache and updated the client to the current version.",
      ["Close the application", "Clear its cache (with your approval)", "Install the latest version from Software Center", "Restart the laptop"],
      "Outdated client with a corrupted cache.", {"medium": 7, "high": 2, "low": 1}, 0.5, "clear_application_cache"),
    # ---------------- Hardware ----------------
    T("Hardware", "display_issue", ["External monitors not detected", "Second screen flickers", "Dock not showing displays"],
      ["Docked at a hot desk and both monitors stay black.",
       "The second monitor flickers every few seconds.",
       "Monitors on the dock are not detected after the update."],
      "Power-cycle dock and update firmware", "Power-cycled the dock and installed the dock firmware and graphics driver from Software Center.",
      ["Unplug the dock power for 10 seconds", "Press Windows key + P and choose Extend", "Install dock firmware and graphics driver", "Restart the laptop"],
      "Outdated dock firmware.", {"medium": 6, "low": 4}, 0.55),
    T("Hardware", "battery_issue", ["Laptop not charging", "Battery drains in two hours", "Charger light off"],
      ["The laptop shows plugged in but not charging.",
       "Battery goes from full to empty in two hours.",
       "The charger light is off and the laptop will not charge."],
      "Replace charger / battery check", "Tested with a known-good charger; replaced the faulty charger and ran a battery health report.",
      ["Try a different wall socket", "Charge directly from the laptop port, not through the dock", "Collect a replacement charger from the IT desk"],
      "Faulty charger.", {"medium": 5, "low": 4, "high": 1}, 0.2),
    T("Hardware", "peripheral_issue", ["Headset microphone not working", "Wireless mouse lagging", "Webcam shows black screen"],
      ["Nobody can hear me in calls with the headset.",
       "The wireless mouse lags and jumps around.",
       "Webcam shows a black image in Teams."],
      "Select device and check privacy settings", "Selected the headset in Teams device settings and allowed desktop apps to use the microphone and camera.",
      ["Pick the headset in the meeting app's device settings", "Check the mute switch", "Allow desktop apps to use the microphone and camera"],
      "Wrong audio device selected; camera privacy setting off.", {"low": 6, "medium": 4}, 0.6),
    T("Hardware", "laptop_hardware_failure", ["Laptop screen cracked", "Keyboard keys not working", "Laptop does not power on"],
      ["Dropped my laptop and the screen has lines across it.",
       "Several keys on the keyboard stopped working.",
       "Laptop does not turn on even when charging."],
      "Hardware repair / loan laptop", "Issued a loan laptop and sent the device for repair under warranty.",
      ["Back up open work to OneDrive", "Bring the laptop to the IT desk", "Collect a loan laptop while it is repaired"],
      "Physical damage.", {"high": 5, "medium": 5}, 0.0),
    # ---------------- Network ----------------
    T("Network", "wifi_connectivity", ["Office Wi-Fi drops", "Cannot join ACME-CORP Wi-Fi", "Wi-Fi connected, no internet"],
      ["Wi-Fi in the third-floor meeting rooms keeps dropping.",
       "My laptop will not join the ACME-CORP network any more.",
       "Laptop shows connected to Wi-Fi but nothing loads."],
      "Rejoin Wi-Fi and renew certificate", "Forgot and rejoined ACME-CORP, flushed DNS and renewed the device certificate over a wired connection.",
      ["Forget ACME-CORP and join again", "Flush the DNS cache (with your approval)", "Restart on a wired connection to renew the certificate"],
      "Expired device certificate on the laptop.", {"medium": 6, "high": 2, "low": 2}, 0.55, "flush_dns_cache"),
    T("Network", "network_slow", ["Teams calls choppy", "SharePoint downloads very slow", "Network slow on 2nd floor"],
      ["Video calls freeze and audio drops since this week.",
       "Downloading files from SharePoint takes ages.",
       "Everything on the network is slow on the second floor."],
      "Wired connection and bandwidth checks", "Moved the user to a wired port and paused a large OneDrive sync; access point on the floor was rebooted.",
      ["Use a wired port where possible", "Pause large cloud sync uploads during calls", "Turn off video when the network is busy"],
      "Busy access point and background sync.", {"medium": 6, "low": 3, "high": 1}, 0.4),
    # ---------------- Printer ----------------
    T("Printer", "printer_not_printing", ["Print jobs stuck in queue", "Printer shows offline", "FollowMe job not released"],
      ["Jobs stay in the print queue and nothing comes out.",
       "The printer near finance shows offline on my laptop.",
       "Tapped my badge but the printer shows no jobs."],
      "Restart print spooler and resend", "Restarted the print spooler, cleared the stuck jobs and printed again to FollowMe.",
      ["Restart the print spooler (with your approval)", "Clear stuck jobs", "Print again to the FollowMe queue", "Tap your badge at any printer"],
      "Stuck spooler on the laptop.", {"medium": 6, "low": 4}, 0.75, "restart_print_spooler"),
    T("Printer", "paper_jam", ["Paper jam on 3rd floor printer", "Printer keeps jamming", "Scanner feeder jams"],
      ["The third-floor printer says paper jam but I cannot see any paper.",
       "Printer jams every few pages.",
       "The document feeder jams on every scan."],
      "Clear jam and service tray", "Cleared paper from tray 2 and the rear door; Print Services replaced the worn feed roller.",
      ["Open the rear door and remove paper", "Check tray 2", "Use fresh, dry paper", "Report repeated jams so the roller can be replaced"],
      "Worn feed roller.", {"low": 7, "medium": 3}, 0.3),
    T("Printer", "printer_driver", ["Printing garbled text", "Cannot add plotter", "Scan to email not arriving"],
      ["My printouts are full of strange symbols.",
       "Need the design plotter added to my laptop.",
       "Scans sent to my email never arrive."],
      "Reinstall printer from Software Center", "Removed the printer and reinstalled it from Software Center with the current driver.",
      ["Remove the printer", "Install it again from Software Center", "Print a test page"],
      "Outdated driver after a Windows update.", {"low": 6, "medium": 4}, 0.5, "restart_print_spooler"),
    # ---------------- Security ----------------
    T("Security", "phishing_report", ["Suspicious email from 'IT support'", "Fake invoice email", "Got a gift card request from 'CEO'"],
      ["Received an email asking me to re-enter my password on a strange website.",
       "Invoice email from a supplier we do not use with a zip attachment.",
       "Someone pretending to be our CEO asked me to buy gift cards."],
      "Report phishing and block sender", "Message removed from all mailboxes and the sender domain blocked; user had not clicked.",
      ["Use the Report phishing button", "Do not click links or open attachments", "Delete the message"],
      "Phishing campaign.", {"high": 6, "medium": 4}, 0.0),
    T("Security", "unauthorized_access", ["Unexpected MFA prompts at night", "Unusual sign-in alert", "Mailbox rule I did not create"],
      ["My phone showed several sign-in approvals I did not start.",
       "Got an unusual sign-in alert from another country.",
       "Found a rule forwarding my mail to an outside address."],
      "Reset password and revoke sessions", "Security signed out all sessions, user reset the password and the forwarding rule was removed.",
      ["Deny prompts you did not start", "Reset your password from a trusted device", "Report the time of the prompts"],
      "Password reused on a breached site.", {"high": 7, "critical": 3}, 0.0),
    # ---------------- Database ----------------
    T("Database", "database_access", ["Need read access to sales reporting DB", "Login failed for reporting database", "SQL client SSL error"],
      ["Please give me read-only access to the sales reporting database.",
       "My access was approved yesterday but I still get login failed.",
       "DBeaver gives a certificate error when connecting to the reporting replica."],
      "Grant access / update driver", "Added the user to the reporting read-only group and updated the SQL client driver.",
      ["Raise a database access request", "Sign out and in again after approval", "Update the SQL client from Software Center"],
      "Access group missing; outdated driver.", {"medium": 6, "low": 3, "high": 1}, 0.2),
    T("Database", "database_performance", ["Month-end report times out", "Dashboard very slow", "Query timeout on reporting server"],
      ["The month-end finance report times out after five minutes.",
       "Sales dashboard takes minutes to load today.",
       "My query keeps hitting the statement timeout."],
      "Index and query tuning", "Added a missing index on the transactions date column and rescheduled the overnight load.",
      ["Narrow the date range", "Run heavy queries on the reporting copy", "Report the report name and time to the Database Team"],
      "Missing index after a schema change.", {"high": 6, "medium": 4}, 0.0),
    # ---------------- Server ----------------
    T("Server", "server_outage", ["Intranet shows 503", "HR portal 502 Bad Gateway", "Timesheet app not loading"],
      ["The intranet shows 503 Service Unavailable.",
       "HR portal gives 502 Bad Gateway for everyone in our team.",
       "The timesheet application does not load at all."],
      "Restart application pool", "Server Operations restarted the application pool and cleared a full log disk.",
      ["Check the IT status page", "Report the error number and time", "Wait for the status page update"],
      "Log disk full on the application server.", {"high": 6, "critical": 2, "medium": 2}, 0.0),
    T("Server", "disk_space", ["S: drive missing", "Access denied on shared folder", "Need a deleted file restored"],
      ["The S: drive is gone since I started working from home.",
       "Access denied when opening the finance shared folder.",
       "I deleted a folder on the team share by mistake."],
      "Remap drive / restore previous version", "Connected the VPN and signed in again to remap the drive; restored the folder from Previous Versions.",
      ["Connect to the VPN", "Sign out and sign in again", "Use Previous Versions to restore files"],
      "Signed in before the VPN was connected.", {"medium": 6, "low": 4}, 0.5),
]

# Past incidents: (days ago, category, title, team, root cause, fix, minutes to resolve, reports, template intent)
INCIDENTS = [
    (62, "Email", "Outlook cannot connect - mail gateway outage", "EMAIL",
     "Expired TLS certificate on the mail gateway.", "Renewed the gateway certificate and restarted the mail transport service.", 150, 9, "outlook_crash"),
    (38, "VPN", "VPN gateway refusing new connections", "NETWORK",
     "Licence pool on the VPN gateway exhausted after a client update.", "Released stale sessions and raised the licence pool; client update paused.", 95, 12, "vpn_connection_failure"),
    (19, "Printer", "Third-floor printers offline after print server patch", "PRINT",
     "Print server patch reset the printer port configuration.", "Restored the port configuration and restarted the print server.", 120, 6, "printer_not_printing"),
    (8, "Network", "Second-floor Wi-Fi down", "NETWORK",
     "Access point controller failed over to a misconfigured standby.", "Restored the primary controller and rebooted the floor access points.", 70, 5, "wifi_connectivity"),
]
INCIDENT_LINES = {
    "outlook_crash": ["Outlook says disconnected and will not load mail.", "Cannot get email, Outlook keeps trying to connect.",
                      "Outlook stuck on 'Trying to connect' since a few minutes."],
    "vpn_connection_failure": ["VPN cannot connect, says gateway unreachable.", "VPN fails to connect, tried three times.",
                               "Cannot connect to the VPN from home at all."],
    "printer_not_printing": ["None of the 3rd floor printers are printing.", "3rd floor printer shows offline for everyone.",
                             "Printing on floor 3 not working."],
    "wifi_connectivity": ["Wi-Fi on the second floor is down.", "No Wi-Fi in the 2nd floor meeting rooms.",
                          "Second floor Wi-Fi disconnected for everyone near me."],
}

SOURCES = ["ai_chatbot"] * 9 + ["portal"]
IMPACT = {"low": "Single user, work can continue", "medium": "Single user, work affected",
          "high": "Work blocked or several people affected", "critical": "Business-critical service affected"}
REASON = {"low": "A workaround exists and nothing is due", "medium": "Slows down the person's daily work",
          "high": "Blocks the person's work or a deadline", "critical": "Many people or a key business service affected"}
# Personal context people add, so no two reports read exactly alike
CONTEXT = ["", "", "Working from home today.", "Windows 11 laptop.", "Already restarted once.", "Started this morning.",
           "It was fine yesterday.", "I have a client call in an hour.", "MacBook.", "Same thing happened last month.",
           "At the Mumbai office today.", "Tried on Wi-Fi and on the cable."]


def _weighted(rng: random.Random, weights: dict):
    keys = list(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys])[0]


def _when(rng: random.Random, now: datetime, days: int, min_age_hours: float = 2) -> datetime:
    while True:
        day = now - timedelta(days=rng.randint(0, days - 1))
        if rng.random() > WEEKDAY_WEIGHTS[day.weekday()] / max(WEEKDAY_WEIGHTS):
            continue
        hour = _weighted(rng, HOUR_WEIGHTS)
        moment = day.replace(hour=hour, minute=rng.randint(0, 59), second=rng.randint(0, 59), microsecond=0)
        if moment <= now - timedelta(hours=min_age_hours):
            return moment


class _Builder:
    """Collects rows and the text fix-ups that need final ticket numbers."""

    def __init__(self, db, ref: dict, rng: random.Random):
        self.db, self.ref, self.rng = db, ref, rng
        self.settings = get_settings()
        self.fixups: list[Callable[[], None]] = []
        self.solutions: dict[str, TicketSolution] = {}
        self.cats: dict[str, TicketCategory] = ref["categories"]
        self.depts = ref["departments"]
        self.staff_by_dept: dict[int, list[User]] = {}
        self.docs: dict[int, KnowledgeDocument] = {}
        self.tickets: dict[int, Ticket] = {}
        self._pending: list[Ticket] = []

    def register(self) -> None:
        """Index tickets by id once they have been flushed."""
        for t in self._pending:
            self.tickets[t.id] = t
        self._pending.clear()

    # ---------------- people ----------------
    async def people(self) -> list[User]:
        roles = {u.role_name: u.role for u in self.ref["users"].values()}
        employees: list[User] = [u for u in self.ref["users"].values() if u.role_name == "employee"]
        names = [(f, l) for f in FIRST for l in LAST]
        self.rng.shuffle(names)
        names.remove(("Aarav", "Kulkarni"))
        names.insert(0, ("Aarav", "Kulkarni"))
        first_names: set[str] = set()
        now = utcnow()
        for first, last in names:
            if len(first_names) >= 45:
                break
            if first in first_names:  # one person per first name keeps the list easy to tell apart
                continue
            first_names.add(first)
            username = f"{first}.{last}".lower()
            unit = self.rng.choice(BUSINESS_UNITS)
            u = User(username=username, email=f"{username}@example.com", full_name=f"{first} {last}", role=roles["employee"],
                     department=self.depts[unit], job_title=self.rng.choice(TITLES[unit]), location=self.rng.choice(LOCATIONS),
                     password_hash=_demo_hash(), created_at=now - timedelta(days=self.rng.randint(120, 900)),
                     last_login_at=now - timedelta(hours=self.rng.randint(2, 24 * 20)))
            self.db.add(u)
            employees.append(u)
        for username, full, role, team, title in EXTRA_STAFF:
            self.db.add(User(username=username, email=f"{username}@example.com", full_name=full, role=roles[role],
                             department=self.depts[team], job_title=title, location="Pune HQ", password_hash=_demo_hash(),
                             created_at=now - timedelta(days=400), last_login_at=now - timedelta(hours=self.rng.randint(1, 30))))
        await self.db.flush()
        staff = (await self.db.execute(select(User))).unique().scalars().all()
        for u in staff:
            if u.role_name == "it_support" and u.department_id:
                self.staff_by_dept.setdefault(u.department_id, []).append(u)
        for d in (await self.db.execute(select(KnowledgeDocument).order_by(KnowledgeDocument.id))).unique().scalars():
            if d.category_id is not None:
                self.docs.setdefault(d.category_id, d)
        return employees

    def staff_for(self, cat: TicketCategory) -> Optional[User]:
        team = self.staff_by_dept.get(cat.department_id) or self.staff_by_dept.get(self.depts["SERVICE_DESK"].id) or []
        return self.rng.choice(team) if team else None

    # ---------------- rows ----------------
    def ticket(self, user: User, tpl: Template, created: datetime, priority: str, variant: int) -> Ticket:
        cat = self.cats[tpl.category]
        title = tpl.titles[variant % len(tpl.titles)]
        desc = f"{tpl.descriptions[variant % len(tpl.descriptions)]} {self.rng.choice(CONTEXT)}".strip()
        label = next((i[2] for i in _intents() if i[0] == tpl.intent), None)
        t = Ticket(ticket_number=f"TMP-{self.rng.getrandbits(48):012x}", user_id=user.id, title=title, description=desc,
                   category_id=cat.id, sub_category=label, intent=tpl.intent, entities=dict(tpl.entities),
                   ai_confidence=round(self.rng.uniform(0.78, 0.97), 2), classification_method="rules",
                   system_priority=priority, priority=priority, priority_confidence=0.85,
                   priority_impact=IMPACT[priority], priority_reason=REASON[priority],
                   status=TicketStatus.AI_ANALYSIS, source=self.rng.choice(SOURCES),
                   extra_data={"demo": True}, created_at=created, updated_at=created)
        if self.rng.random() < 0.25:
            t.user_priority = self.rng.choice(["medium", "high"]) if priority != "critical" else "critical"
        self.db.add(t)
        self._pending.append(t)
        return t

    def event(self, t: Ticket, kind: str, at: datetime, description: str, user: Optional[User] = None, new=None):
        self.db.add(TicketEvent(ticket_id=t.id, user_id=user.id if user else None, event_type=kind, new_value=new,
                                description=description, created_at=at))

    def step(self, t: Ticket, run: Optional[AgentRun], key: str, title: str, detail: str, at: datetime,
             by: str = "agent", user: Optional[User] = None) -> TroubleshootingStep:
        s = TroubleshootingStep(ticket_id=t.id, agent_run_id=run.id if run else None, step_key=key, title=title,
                                detail=detail, performed_by=by, created_by=user.id if user else None, created_at=at)
        self.db.add(s)
        return s

    def message(self, t: Ticket, role: str, content: str, at: datetime, user: Optional[User] = None,
                payload: Optional[dict] = None, internal: bool = False) -> TicketMessage:
        m = TicketMessage(ticket_id=t.id, user_id=user.id if user else None, role=role, content=content,
                          payload=payload or {}, is_internal=internal, created_at=at)
        self.db.add(m)
        return m

    async def run(self, t: Ticket, at: datetime, level: str, status: str, end: datetime, hits: int) -> AgentRun:
        run = AgentRun(ticket_id=t.id, state=status, attempt=1, routing_level=level, llm_calls=0, tokens_used=0,
                       retrieval_hits=hits, confidence=round(self.rng.uniform(0.7, 0.95), 2), resolution_status=status,
                       started_at=at, completed_at=end, latency_ms=round(self.rng.uniform(300, 2500), 1),
                       context={"progress": {"understand": "done", "classify": "done", "priority": "done",
                                             "duplicates": "done", "knowledge": "done", "troubleshoot": "done",
                                             "verify": "done", "outcome": "done"}},
                       reasoning_summary=None)
        self.db.add(run)
        await self.db.flush()
        return run

    def intake(self, t: Ticket, run: AgentRun, user: User, at: datetime, tpl: Template):
        self.message(t, "user", t.description, at, user)
        self.event(t, "ticket_created", at, "Reported through the chat assistant" if t.source == "ai_chatbot"
                   else "Reported through the ticket form", user, t.status)
        self.step(t, run, "understand", "Ticket received", "Problem description captured", at)
        self.step(t, run, "classify", "Category identified",
                  f"{tpl.category}: {t.sub_category} (rules, {round((t.ai_confidence or 0.9) * 100)}% sure)", at + timedelta(seconds=2))
        self.step(t, run, "duplicates", "Checked for similar reports", "No open ticket or incident matched", at + timedelta(seconds=3))

    # ---------------- outcomes ----------------
    async def resolve_by_assistant(self, t: Ticket, tpl: Template, user: User, at: datetime) -> None:
        sol = self.solutions.get(tpl.intent)
        minutes = self.rng.uniform(4, 35)
        end = at + timedelta(minutes=minutes)
        level = "L3_verified_retrieval" if sol else "L1_rules"
        run = await self.run(t, at, level, "resolved", end, hits=2 if sol else 1)
        self.intake(t, run, user, at, tpl)
        if sol:
            title, steps, summary = sol.title, list(sol.steps), sol.solution_description
            sol.times_used += 1
            sol.times_successful += 1
            sources: list[str] = []
        else:
            doc = self.docs.get(self.cats[tpl.category].id)
            title, steps, summary = (doc.title if doc else tpl.fix_title), tpl.steps, tpl.fix
            sources = [f"KB-{doc.id}"] if doc else []
        candidate = {"kind": "solution" if sol else "kb_procedure",
                     "label": "HUMAN-APPROVED SOLUTION" if sol else "VERIFIED SOLUTION", "title": title,
                     "summary": summary, "steps": steps, "routing_level": level, "confidence": run.confidence,
                     "solution_id": sol.id if sol else None, "source_ticket": None, "sources": sources,
                     "automated_actions": [tpl.action] if tpl.action else [], "similarity": round(self.rng.uniform(0.66, 0.9), 2) if sol else None,
                     "model": None, "safety_flags": []}
        reply = self.message(t, "assistant", "Here is a fix that has worked for this problem before. Let me know if it solves it.",
                             at + timedelta(seconds=8), payload={"solution": candidate})
        step = self.step(t, run, "troubleshoot", "Fix found", title, at + timedelta(seconds=8))
        if sol:
            def fix_refs(m=reply, s=step, sol=sol, c=candidate):
                origin = self.tickets.get(sol.ticket_id)
                number = origin.ticket_number if origin else None
                m.payload = {"solution": {**c, "source_ticket": number}}
                s.detail = f"{c['title']} (from {number})" if number else c["title"]
            self.fixups.append(fix_refs)
        if tpl.action and self.rng.random() < 0.8:
            self.db.add(AgentAction(agent_run_id=run.id, ticket_id=t.id, tool_name=tpl.action, permission_level="restricted",
                                    parameters={}, status="approved", approval_required=True, approver_role="requester",
                                    approved_by=user.id, decided_at=at + timedelta(minutes=2), latency_ms=40.0,
                                    result={"ok": True, "mode": "dry_run", "executed": False,
                                            "summary": "Approved by the employee and queued (demo: no device connector)"},
                                    created_at=at + timedelta(seconds=9)))
            spec = get_tool(tpl.action)
            self.step(t, run, "troubleshoot", f"Executed: {spec.label if spec else tpl.action}",
                      "Approved by the employee", at + timedelta(minutes=2))
        self.event(t, "status_changed", at + timedelta(seconds=8), "Fix suggested to the employee", None, TicketStatus.AWAITING_USER)
        self.step(t, run, "verify", "Fix confirmed", "Employee confirmed the suggested fix worked", end, by="user", user=user)
        self.message(t, "user", "Yes, it's fixed", end, user)
        self.event(t, "status_changed", end, "Employee confirmed the suggested fix worked", user, TicketStatus.RESOLVED)
        rating = _weighted(self.rng, {5: 55, 4: 35, 3: 10})
        self.db.add(TicketFeedback(ticket_id=t.id, user_id=user.id, solution_id=sol.id if sol else None, issue_resolved=True,
                                   satisfaction_rating=rating, created_at=end))
        t.status, t.resolved_by_ai, t.resolved_at, t.updated_at = TicketStatus.RESOLVED, True, end, end
        t.resolution_summary = summary

    async def resolve_by_staff(self, t: Ticket, tpl: Template, user: User, at: datetime, *, open_state: Optional[str] = None,
                               failed_first: bool = False) -> None:
        cat = self.cats[tpl.category]
        dept = next(d for d in self.depts.values() if d.id == cat.department_id)
        agent = self.staff_for(cat)
        lo, hi = STAFF_HOURS[t.priority]
        hours = self.rng.uniform(lo, hi) * (1.8 if self.rng.random() < 0.1 else 1.0)  # a few run over target
        end = at + timedelta(hours=hours)
        state = open_state or "resolved"
        run = await self.run(t, at, "L3_verified_retrieval" if failed_first else "L1_rules", "escalated",
                             at + timedelta(minutes=1), hits=1 if failed_first else 0)
        self.intake(t, run, user, at, tpl)
        esc_at = at + timedelta(minutes=self.rng.uniform(1, 25) if failed_first else 0.5)
        if failed_first and tpl.intent in self.solutions:
            sol = self.solutions[tpl.intent]
            sol.times_used += 1
            sol.times_failed += 1
            self.step(t, run, "troubleshoot", "Fix found", sol.title, at + timedelta(seconds=8))
            self.step(t, run, "verify", "Fix did not work", "Employee said the problem is still there", esc_at, by="user", user=user)
            self.db.add(TicketFeedback(ticket_id=t.id, user_id=user.id, solution_id=sol.id, issue_resolved=False,
                                       satisfaction_rating=self.rng.choice([2, 3]), comments="Still not working", created_at=esc_at))
            reason = "Suggested fix did not work"
        else:
            reason = "No verified fix for this problem" if tpl.ai_share else "Needs IT staff (hands-on or security review)"
        self.step(t, run, "outcome", "Passed to IT staff", f"{dept.name}: {reason.lower()}", esc_at)
        esc = TicketEscalation(ticket_id=t.id, department_id=dept.id, reason=reason, created_at=esc_at,
                               package={"summary": t.title, "category": tpl.category, "priority": t.priority,
                                        "requester": user.full_name, "troubleshooting_attempted": failed_first})
        self.db.add(esc)
        self.fixups.append(lambda e=esc, t=t: setattr(e, "package", {**e.package, "ticket_id": t.ticket_number}))
        self.event(t, "escalated", esc_at, f"Escalated to {dept.name}: {reason}", None, TicketStatus.ESCALATED)
        self.message(t, "assistant", f"I have passed this to the {dept.name} with the details so far.", esc_at + timedelta(seconds=2))
        t.department_id, t.status, t.updated_at = dept.id, TicketStatus.ESCALATED, esc_at
        if state == "escalated" or agent is None:
            return
        take = esc_at + timedelta(minutes=self.rng.uniform(5, 50))
        t.assigned_to, t.status, t.updated_at = agent.id, TicketStatus.ASSIGNED, take
        self.db.add(TicketAssignment(ticket_id=t.id, assigned_by=agent.id, assigned_to=agent.id, reason="Accepted", created_at=take))
        self.event(t, "assigned", take, f"Assigned to {agent.full_name}", agent, agent.full_name)
        if state == "assigned":
            return
        work = take + timedelta(minutes=self.rng.uniform(2, 20))
        t.status, t.updated_at = TicketStatus.IN_PROGRESS, work
        self.event(t, "status_changed", work, "Work started", agent, TicketStatus.IN_PROGRESS)
        self.message(t, "agent", f"Hi {user.full_name.split()[0]}, I'm looking at this now.", work, agent)
        if state == "in_progress":
            return
        end = max(end, work + timedelta(minutes=10))
        self.step(t, None, "manual", "Resolved by IT", tpl.fix, end, by="it_support", user=agent)
        self.message(t, "agent", f"{tpl.fix} Please let me know if anything is still not right.", end, agent)
        self.event(t, "status_changed", end, "Resolved by IT support", agent, TicketStatus.RESOLVED)
        t.status, t.resolved_at, t.updated_at, t.resolution_summary = TicketStatus.RESOLVED, end, end, tpl.fix
        if self.rng.random() < 0.6:
            self.db.add(TicketFeedback(ticket_id=t.id, user_id=user.id, issue_resolved=True,
                                       satisfaction_rating=_weighted(self.rng, {5: 45, 4: 40, 3: 15}), created_at=end + timedelta(hours=1)))
        if tpl.intent not in self.solutions and tpl.ai_share > 0:
            sol = TicketSolution(ticket_id=t.id, category_id=cat.id, intent=tpl.intent, title=tpl.fix_title,
                                 problem_description=t.description, root_cause=tpl.root_cause, solution_description=tpl.fix,
                                 steps=tpl.steps, automated_actions=[tpl.action] if tpl.action else [],
                                 confidence_level="human_verified", source="it_support", times_used=1, times_successful=1,
                                 created_by=agent.id, verified_by=agent.id, verified_at=end, created_at=end, updated_at=end)
            self.db.add(sol)
            await self.db.flush()
            self.solutions[tpl.intent] = sol

    async def duplicate(self, original: Ticket, tpl: Template, user: User, at: datetime) -> Ticket:
        t = self.ticket(user, tpl, at, original.priority, self.rng.randint(0, 5))
        await self.db.flush()
        run = await self.run(t, at, "L2_similarity", "duplicate", at + timedelta(seconds=5), hits=1)
        self.intake(t, run, user, at, tpl)
        t.duplicate_of_id, t.status = original.id, TicketStatus.DUPLICATE
        t.resolved_at = t.updated_at = at + timedelta(seconds=5)
        step = self.step(t, run, "duplicates", "Already reported", "Same problem as an earlier ticket", at + timedelta(seconds=4))
        ev = TicketEvent(ticket_id=t.id, event_type="duplicate_linked", description="Same problem as an earlier ticket",
                         created_at=at + timedelta(seconds=4))
        self.db.add(ev)

        def fix(s=step, e=ev, o=original):
            s.detail = e.description = f"Same problem as {o.ticket_number}"
        self.fixups.append(fix)
        return t

    async def incident(self, days_ago: int, category: str, title: str, team: str, root: str, fix: str, minutes: int,
                       reports: int, intent: str, employees: list[User], now: datetime, n: int) -> None:
        cat = self.cats[category]
        start = (now - timedelta(days=days_ago)).replace(hour=5, minute=self.rng.randint(0, 40), second=0, microsecond=0)
        resolved = start + timedelta(minutes=minutes)
        inc = Incident(incident_number=f"INCIDENT-{category.upper()}-{n:03d}", title=title, category_id=cat.id, priority="high",
                       status="resolved", department_id=self.depts[team].id, root_cause=root, resolution=fix,
                       detection_similarity=round(self.rng.uniform(0.62, 0.81), 3), first_reported=start,
                       last_reported=start + timedelta(minutes=reports * 4), resolved_at=resolved, created_at=start + timedelta(minutes=8))
        self.db.add(inc)
        await self.db.flush()
        tpl = next(t for t in TEMPLATES if t.intent == intent)
        for k, user in enumerate(self.rng.sample(employees, reports)):
            at = start + timedelta(minutes=k * 4 + self.rng.randint(0, 3))
            t = self.ticket(user, tpl, at, "high", k)
            t.title, t.description = title.split(" - ")[0] if k == 0 else tpl.titles[k % len(tpl.titles)], INCIDENT_LINES[intent][k % 3]
            await self.db.flush()
            linked = k >= 2  # the third similar report opens the incident; earlier ones are linked to it
            run = await self.run(t, at, "L2_similarity", "linked_incident", at + timedelta(seconds=5), hits=1)
            self.intake(t, run, user, at, tpl)
            link_at = max(at, inc.created_at) if not linked else at + timedelta(seconds=5)
            self.step(t, run, "duplicates", "Linked to a known problem", f"Grouped into {inc.incident_number}", link_at)
            self.event(t, "linked_to_incident", link_at, f"Grouped into {inc.incident_number}", None, inc.incident_number)
            self.event(t, "status_changed", resolved, f"Resolved via {inc.incident_number}", None, TicketStatus.RESOLVED)
            t.incident_id, t.department_id, t.status = inc.id, self.depts[team].id, TicketStatus.RESOLVED
            t.resolved_at, t.updated_at, t.resolution_summary = resolved, resolved, fix


_HASH: dict[str, str] = {}


def _demo_hash() -> str:
    # One bcrypt hash shared by every generated account keeps seeding fast; each is still a normal bcrypt hash.
    if "h" not in _HASH:
        _HASH["h"] = hash_password(DEMO_PASSWORD)
    return _HASH["h"]


def _intents():
    from app.services.classification import INTENTS
    return INTENTS


async def seed_demo_org(db, ref: dict, *, days: int = 90, tickets: int = 330) -> dict:
    """Add the demo organisation and a quarter of ticket history. Returns counts (or {} if already present)."""
    if (await db.execute(select(User.id).where(User.username == MARKER_USERNAME))).first():
        return {}
    rng = random.Random(42)
    b = _Builder(db, ref, rng)
    employees = await b.people()
    now = utcnow()
    # People whose reports are replayed live during seeding: keep their recent history quiet so the
    # replay is not flagged as duplicates of generated tickets.
    live_users = {"bcooper", "ewhite", "fzhang", "gadams", "kwright"}

    for n, (days_ago, *rest) in enumerate(INCIDENTS):
        same_cat = sum(1 for i in INCIDENTS[:n] if i[1] == rest[0])
        await b.incident(days_ago, *rest, employees=employees, now=now, n=same_cat + 1)

    moments = sorted(_when(rng, now, days) for _ in range(tickets))
    by_cat = {c: [t for t in TEMPLATES if t.category == c] for c in CATEGORY_WEIGHTS}
    made: list[tuple[Ticket, Template, User]] = []
    counts = {"resolved_by_assistant": 0, "resolved_by_it": 0, "open": 0, "duplicates": 0}
    for at in moments:
        tpl = rng.choice(by_cat[_weighted(rng, CATEGORY_WEIGHTS)])
        age_hours = (now - at).total_seconds() / 3600
        recent = age_hours < 96  # the last few working days still have tickets with IT
        pool = [u for u in employees if not (recent and u.username in live_users)]
        user = rng.choice(pool)
        # A few people raise a lot of tickets; John Doe gets a realistic personal history for the demo
        if rng.random() < 0.025:
            user = next(u for u in employees if u.username == "johndoe")
        if made and rng.random() < 0.04 and not recent:
            orig, otpl, ouser = made[-1]
            if (at - orig.created_at).total_seconds() < 86400 and orig.status != TicketStatus.DUPLICATE:
                await b.duplicate(orig, otpl, ouser, at)
                counts["duplicates"] += 1
                continue
        priority = _weighted(rng, tpl.priorities)
        t = b.ticket(user, tpl, at, priority, rng.randint(0, 5))
        await db.flush()
        if recent and user.username != "johndoe" and rng.random() < 0.55:
            await b.resolve_by_staff(t, tpl, user, at, open_state=rng.choice(["escalated", "assigned", "in_progress"]))
            counts["open"] += 1
        elif recent and user.username == "johndoe" and tpl.category == "Hardware" and rng.random() < 0.5:
            await b.resolve_by_staff(t, tpl, user, at, open_state="in_progress")
            counts["open"] += 1
        elif tpl.intent in b.solutions and rng.random() < tpl.ai_share:
            await b.resolve_by_assistant(t, tpl, user, at)
            counts["resolved_by_assistant"] += 1
        elif tpl.ai_share and tpl.intent not in b.solutions and rng.random() < 0.25:
            await b.resolve_by_assistant(t, tpl, user, at)  # answered from the knowledge-base article
            counts["resolved_by_assistant"] += 1
        elif age_hours < 14 * 24 and user.username not in live_users and rng.random() < 0.3:
            # Still being worked on (waiting for parts, a vendor or the requester)
            await b.resolve_by_staff(t, tpl, user, at, open_state=rng.choice(["assigned", "in_progress"]))
            counts["open"] += 1
        else:
            await b.resolve_by_staff(t, tpl, user, at, failed_first=tpl.intent in b.solutions and rng.random() < 0.3)
            counts["resolved_by_it"] += 1
        made.append((t, tpl, user))

    await db.flush()
    b.register()
    await renumber_tickets(db, now)
    for fix in b.fixups:
        fix()
    await db.flush()
    counts["employees_added"] = len([u for u in employees if u.email.endswith("@example.com")]) - len(
        [u for u in ref["users"].values() if u.role_name == "employee"])
    counts["incidents"] = len(INCIDENTS)
    counts["verified_fixes"] = len(b.solutions)
    return counts


async def renumber_tickets(db, now: datetime) -> None:
    """Number all tickets in the order they were reported (INC-000001 is the oldest).

    Core UPDATEs with an explicit updated_at, so the ORM's onupdate does not stamp every ticket
    with the seeding time; tickets the seed touched without a meaningful update time get their
    resolution (or creation) time instead."""
    await db.flush()
    rows = (await db.execute(select(Ticket).order_by(Ticket.created_at, Ticket.id))).unique().scalars().all()
    seeded_recently = now - timedelta(minutes=10)
    for t in rows:
        await db.execute(update(Ticket).where(Ticket.id == t.id).values(ticket_number=f"TMP-{t.id}", updated_at=t.updated_at)
                         .execution_options(synchronize_session=False))
    for i, t in enumerate(rows, 1):
        number = f"INC-{i:06d}"
        stamp = t.updated_at
        if _aware(stamp) >= seeded_recently and _aware(t.created_at) < seeded_recently:
            stamp = t.resolved_at or t.created_at
        await db.execute(update(Ticket).where(Ticket.id == t.id).values(ticket_number=number, updated_at=stamp)
                         .execution_options(synchronize_session=False))
        set_committed_value(t, "ticket_number", number)
        set_committed_value(t, "updated_at", stamp)
    numbers = {t.id: t.ticket_number for t in rows}
    for esc in (await db.execute(select(TicketEscalation))).unique().scalars():
        if isinstance(esc.package, dict) and "ticket_id" in esc.package and esc.ticket_id in numbers:
            esc.package = {**esc.package, "ticket_id": numbers[esc.ticket_id]}


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
