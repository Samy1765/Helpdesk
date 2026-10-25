"""
Precision AI - Demo company: Acme Demo Industries (fictional).

Loaded by `python -m app.database.seed` when SEED_DEMO_DATA=true (the Docker default). It turns the small
reference seed into a believable quarter for a live demo:

  * 60 employees in 15 business units, 11 IT staff, 2 administrators, one deactivated leaver
  * ~340 tickets over the last 90 days across all ten categories: office-hours peaks (IST), Monday spikes,
    quiet weekends; resolved by verified-knowledge reuse (L3), documented procedures, IT engineers after
    escalation, policy escalation (L0), duplicates (L2) and incident correlation
  * four historical incidents (e-mail, VPN, printing, Bengaluru Wi-Fi), each resolved, with linked tickets
  * approvals for restricted actions, employee feedback and SLA outcomes for the admin charts
  * a few tickets still open right now (escalated, waiting for the employee, waiting for an approval)

Everything comes from a fixed random seed, so every run builds the same company, and a marker row in the
audit log makes the seed idempotent. All names, addresses and incidents are invented. No LLM usage is
fabricated: demo tickets were handled by the deterministic levels and by people, so LLM charts only show
calls that really happened.
"""

import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.agents.state_machine import PROGRESS_STEPS
from app.core.config import get_settings
from app.core.security import hash_password
from app.database.session import utcnow
from app.models import (
    AgentAction, AgentRun, AuditLog, Department, Incident, Role, SolutionConfidence, Ticket, TicketAssignment,
    TicketCategory, TicketEscalation, TicketEvent, TicketFeedback, TicketMessage, TicketSolution, TicketStatus,
    TroubleshootingStep, User,
)
from app.services.classification import INTENT_LABELS
from app.services.knowledge import chunk_markdown, is_procedure, steps_from_text
from app.tools.registry import get_tool

COMPANY = "Acme Demo Industries"
DOMAIN = "acme-demo.in"
MARKER = "demo_company_seeded"
DEMO_PASSWORD = "Employee@123"
IST = timezone(timedelta(hours=5, minutes=30))
QUARTER_DAYS = 90
RNG_SEED = 20261025

# Ten business units added to the five in the reference seed -> 15 business units
BUSINESS_UNITS = [
    ("Marketing", "BU_MARKETING"), ("Operations", "BU_OPERATIONS"), ("Legal & Compliance", "BU_LEGAL"),
    ("Procurement", "BU_PROCUREMENT"), ("Customer Support", "BU_CUSTOMER_SUPPORT"), ("Supply Chain", "BU_SUPPLY_CHAIN"),
    ("Quality Assurance", "BU_QUALITY"), ("Manufacturing", "BU_MANUFACTURING"), ("Facilities", "BU_FACILITIES"),
    ("Research & Development", "BU_RND"),
]

# username, full name, role, department code, job title, location
STAFF = [
    ("it.manager", "Nisha Raghavan", "admin", "SERVICE_DESK", "IT Service Manager", "Pune HQ"),
    ("desk2.agent", "Karan Malhotra", "it_support", "SERVICE_DESK", "Service Desk Analyst", "Bengaluru Office"),
]
EMPLOYEES = [
    ("Ishaan Kulkarni", "BU_ENGINEERING", "Platform Engineer", "Pune HQ"),
    ("Meera Iyer", "BU_DESIGN", "Visual Designer", "Bengaluru Office"),
    ("Rohan Bhatt", "BU_DESIGN", "Interaction Designer", "Pune HQ"),
    ("Ananya Rao", "BU_SALES", "Key Account Manager", "Bengaluru Office"),
    ("Vikram Sethi", "BU_SALES", "Inside Sales Executive", "Remote"),
    ("Pooja Deshpande", "BU_HR", "Payroll Coordinator", "Pune HQ"),
    ("Farhan Qureshi", "BU_HR", "Talent Acquisition Specialist", "Bengaluru Office"),
    ("Sneha Kapoor", "BU_MARKETING", "Marketing Manager", "Pune HQ"),
    ("Aditya Joshi", "BU_MARKETING", "Content Strategist", "Remote"),
    ("Lakshmi Menon", "BU_MARKETING", "Digital Campaign Analyst", "Bengaluru Office"),
    ("Neil Dsouza", "BU_MARKETING", "Brand Designer", "Pune HQ"),
    ("Rajesh Pillai", "BU_OPERATIONS", "Operations Manager", "Pune HQ"),
    ("Kavya Nambiar", "BU_OPERATIONS", "Process Analyst", "Bengaluru Office"),
    ("Suresh Gowda", "BU_OPERATIONS", "Shift Coordinator", "Chennai Plant"),
    ("Tanvi Shah", "BU_OPERATIONS", "Operations Analyst", "Pune HQ"),
    ("Arjun Saxena", "BU_LEGAL", "Legal Counsel", "Pune HQ"),
    ("Divya Krishnan", "BU_LEGAL", "Compliance Officer", "Bengaluru Office"),
    ("Mohit Agarwal", "BU_LEGAL", "Contracts Manager", "Pune HQ"),
    ("Sanjay Reddy", "BU_PROCUREMENT", "Procurement Lead", "Pune HQ"),
    ("Nandini Bose", "BU_PROCUREMENT", "Buyer", "Chennai Plant"),
    ("Harish Venkat", "BU_PROCUREMENT", "Vendor Manager", "Bengaluru Office"),
    ("Priyanka Das", "BU_CUSTOMER_SUPPORT", "Support Team Lead", "Bengaluru Office"),
    ("Amit Chauhan", "BU_CUSTOMER_SUPPORT", "Support Executive", "Bengaluru Office"),
    ("Ritu Sharma", "BU_CUSTOMER_SUPPORT", "Support Executive", "Remote"),
    ("Zoya Khan", "BU_CUSTOMER_SUPPORT", "Escalations Specialist", "Bengaluru Office"),
    ("Gaurav Mishra", "BU_CUSTOMER_SUPPORT", "Support Executive", "Bengaluru Office"),
    ("Deepak Yadav", "BU_SUPPLY_CHAIN", "Logistics Planner", "Chennai Plant"),
    ("Shalini Murthy", "BU_SUPPLY_CHAIN", "Supply Planner", "Pune HQ"),
    ("Varun Arora", "BU_SUPPLY_CHAIN", "Warehouse Supervisor", "Chennai Plant"),
    ("Ayesha Siddiqui", "BU_SUPPLY_CHAIN", "Demand Planner", "Remote"),
    ("Prakash Jain", "BU_QUALITY", "Quality Manager", "Chennai Plant"),
    ("Swati Patwardhan", "BU_QUALITY", "Quality Engineer", "Chennai Plant"),
    ("Imran Sheikh", "BU_QUALITY", "Inspection Lead", "Chennai Plant"),
    ("Manoj Patil", "BU_MANUFACTURING", "Plant Manager", "Chennai Plant"),
    ("Rekha Subramanian", "BU_MANUFACTURING", "Production Planner", "Chennai Plant"),
    ("Sunil Kamble", "BU_MANUFACTURING", "Line Supervisor", "Chennai Plant"),
    ("Anjali Verma", "BU_MANUFACTURING", "Maintenance Engineer", "Chennai Plant"),
    ("Ganesh Hegde", "BU_MANUFACTURING", "Production Engineer", "Chennai Plant"),
    ("Vinod Nair", "BU_FACILITIES", "Facilities Manager", "Pune HQ"),
    ("Shweta Pandey", "BU_FACILITIES", "Workplace Coordinator", "Bengaluru Office"),
    ("Kiran Bhosale", "BU_RND", "R&D Engineer", "Pune HQ"),
    ("Nikhil Ghosh", "BU_RND", "Firmware Engineer", "Pune HQ"),
    ("Aparna Sen", "BU_RND", "Research Scientist", "Bengaluru Office"),
    ("Yash Thakur", "BU_RND", "Test Engineer", "Remote"),
]
LEAVER = ("Rahul Menon", "BU_SALES", "Regional Sales Manager", "Remote")
# Accounts from the reference seed whose demo scenarios must stay predictable: only closed tickets for them
REFERENCE_EMPLOYEES = {"johndoe", "arivera", "schen", "dmiller", "pnair", "jokafor", "lgarcia", "tbrooks", "mkim",
                       "rpatel", "hsingh", "ewhite", "fzhang", "gadams", "kwright", "bcooper"}


@dataclass
class Template:
    category: str
    intent: str
    weight: float
    titles: list[str]
    reports: list[str]
    priority: tuple[float, float, float, float]  # low, medium, high, critical
    path: str                                     # reuse | kb | human | policy
    solution: Optional[str] = None                # verified solution title (reuse)
    kb: Optional[str] = None                      # knowledge document title (kb)
    fixes: list[str] = field(default_factory=list)  # what the engineer did (human paths)


TEMPLATES = [
    # ---------------- VPN ----------------
    Template("VPN", "vpn_mfa_failure", 5, ["GlobalProtect sign-in fails after Authenticator approval",
             "VPN rejects login after MFA prompt", "Cannot connect to VPN, authentication failed"],
             ["GlobalProtect says authentication failed as soon as I approve the request on my phone. Working from {site} today.",
              "VPN login fails right after the Authenticator number prompt. Tried twice, same error.",
              "Since this morning GlobalProtect goes back to not connected after I approve sign-in on my phone."],
             (0.05, 0.75, 0.2, 0), "reuse", solution="GlobalProtect rejects sign-in after the Authenticator approval",
             fixes=["VPN entitlement had lapsed after a role change; re-granted Remote access (VPN) and confirmed connection."]),
    Template("VPN", "vpn_disconnection", 4, ["VPN keeps disconnecting every few minutes", "GlobalProtect drops during Teams calls"],
             ["The VPN connects but drops every 5-10 minutes, my Teams calls freeze each time.",
              "GlobalProtect keeps reconnecting all afternoon, I lose my file share connection each time."],
             (0.1, 0.75, 0.15, 0), "reuse", solution="GlobalProtect keeps dropping and reconnecting from home",
             fixes=["Home router firmware was dropping long-lived sessions; advised a router update and enabled the backup gateway."]),
    Template("VPN", "vpn_connection_failure", 2.5, ["VPN connected but intranet not opening", "Mapped drives unavailable over VPN"],
             ["GlobalProtect shows connected but Acme Connect and my mapped drives do not open.",
              "On VPN I can browse the internet but none of the internal sites load."],
             (0.1, 0.8, 0.1, 0), "reuse", solution="VPN connected but intranet and mapped drives unreachable"),
    Template("VPN", "vpn_connection_failure", 1.2, ["FortiClient plant VPN not connecting", "Cannot reach plant systems over FortiClient"],
             ["FortiClient for the plant stops at 40% and says the server may be unreachable.",
              "I need to check the line dashboard from home but the plant VPN will not connect."],
             (0.05, 0.6, 0.35, 0), "reuse", solution="FortiClient plant VPN stuck at 40 percent",
             fixes=["Plant VPN access had expired for the user; renewed it with the plant manager's approval."]),
    # ---------------- Network ----------------
    Template("Network", "wifi_connectivity", 4, ["Office Wi-Fi connected but no pages load", "No internet on ACME-CORP Wi-Fi"],
             ["My laptop is on ACME-CORP at {site} but every website times out. People around me are fine.",
              "Wi-Fi shows no internet, secured since I came back from the meeting room."],
             (0.1, 0.8, 0.1, 0), "reuse", solution="ACME-CORP Wi-Fi connected without internet on one laptop",
             fixes=["Access point on the floor had a stuck radio; Network Team restarted it and the laptop reconnected."]),
    Template("Network", "wifi_connectivity", 1.5, ["New laptop cannot join ACME-CORP", "Wi-Fi asks for username and password"],
             ["My replacement laptop cannot join the office Wi-Fi, it asks for a username and password.",
              "ACME-CORP says can't connect to this network on the new laptop."],
             (0.1, 0.85, 0.05, 0), "reuse", solution="New laptop cannot join ACME-CORP and asks for a password"),
    Template("Network", "network_outage", 1.5, ["Desk network port not working", "Dock shows network cable unplugged"],
             ["At hot desk {desk} the wired connection through the dock is not working, Wi-Fi is fine.",
              "Windows says network cable unplugged at my desk on floor 3."],
             (0.3, 0.7, 0, 0), "reuse", solution="Hot desk dock shows network cable unplugged",
             fixes=["Wall port was disabled after a desk move; Network Team re-enabled it on the access switch."]),
    Template("Network", "network_slow", 1.5, ["Network very slow on floor 4", "File share takes minutes to open files"],
             ["Opening files from the finance share takes over a minute since yesterday.",
              "Everything on the network is slow at {site} this afternoon, calls keep dropping."],
             (0.1, 0.6, 0.3, 0), "kb", kb="Network is slow when opening files or loading internal apps",
             fixes=["Backup job was saturating the uplink during office hours; Network Team moved it to 22:00 IST."]),
    # ---------------- Password / MFA ----------------
    Template("Password", "password_reset", 6, ["Password expired, cannot sign in", "Forgot my password after leave"],
             ["Windows says my password has expired and I cannot get into Outlook either.",
              "Back from leave and I don't remember my password. Laptop says the password is incorrect."],
             (0.1, 0.85, 0.05, 0), "reuse", solution="Forgotten or expired password reset through self-service"),
    Template("Password", "account_locked", 5, ["Account locked out again", "Locked out after password change"],
             ["My account is locked again this morning. I changed my password yesterday.",
              "Got locked out twice today, I think my phone still has the old password."],
             (0.05, 0.75, 0.2, 0), "reuse", solution="Account keeps locking after a password change",
             fixes=["Old password cached on a meeting-room PC; signed the user out there and cleared the lockout source."]),
    Template("Password", "mfa_issue", 3, ["New phone, Authenticator not set up", "MFA prompts go to my old phone"],
             ["I changed my phone over the weekend and the Authenticator app has no work account now.",
              "Sign-in keeps asking me to approve on a phone I traded in."],
             (0.05, 0.7, 0.25, 0), "reuse", solution="Authenticator not set up on a new phone",
             fixes=["Old phone already reset; verified identity on a video call and reset the MFA registration."]),
    Template("Password", "mfa_issue", 2, ["Authenticator notifications not arriving", "MFA code rejected"],
             ["Sign-in waits for approval but no notification comes to my phone.",
              "The six-digit code from Authenticator is not accepted."],
             (0.05, 0.75, 0.2, 0), "reuse", solution="Authenticator approvals not arriving on the phone"),
    # ---------------- Email ----------------
    Template("Email", "outlook_crash", 4, ["Outlook crashes on start", "Outlook keeps closing after update"],
             ["Outlook opens and closes after a few seconds since the update this morning.",
              "Outlook says it has stopped working every time I open a calendar invite."],
             (0.05, 0.8, 0.15, 0), "reuse", solution="Outlook closes on start after the monthly Office update",
             fixes=["Office installation was damaged; ran an online repair remotely and rebuilt the profile."]),
    Template("Email", "email_access_failure", 3, ["Outlook keeps asking for password", "Teams and Outlook sign-in loop"],
             ["Outlook keeps showing need password and Teams wants me to sign in again every hour.",
              "After my password change Outlook won't stop asking me to sign in."],
             (0.1, 0.85, 0.05, 0), "reuse", solution="Outlook and Teams keep asking to sign in after a password change"),
    Template("Email", "email_send_receive", 3, ["Email to client bounced", "Message stuck in Outbox"],
             ["My email to a customer came back as undeliverable, it had large drawings attached.",
              "An email has been sitting in my Outbox for an hour and won't send."],
             (0.15, 0.75, 0.1, 0), "reuse", solution="Email bounces back because the attachment is too large",
             fixes=["Recipient domain had blocked our relay; mail team contacted their admin and released the block."]),
    Template("Email", "calendar_sync", 2.5, ["Team calendar not updating", "Shared calendar out of date"],
             ["The shared operations calendar is not updating in Outlook, my phone shows the new meetings.",
              "Meetings booked by my manager don't show in my Outlook calendar."],
             (0.3, 0.7, 0, 0), "reuse", solution="Team calendar stopped updating in Outlook"),
    Template("Email", "calendar_sync", 2, ["Nobody can hear me in Teams meetings", "Teams uses wrong microphone"],
             ["In Teams calls people say they cannot hear me, my headset is plugged into the dock.",
              "Teams keeps switching to the laptop speakers in the middle of meetings."],
             (0.2, 0.8, 0, 0), "reuse", solution="Colleagues cannot hear me in Teams meetings"),
    Template("Email", "email_send_receive", 1, ["Mailbox full, cannot send", "Mailbox size limit exceeded"],
             ["Outlook says my mailbox is over the limit and I can't send anything.",
              "Getting a warning that my mailbox is almost full, then sending stopped."],
             (0.1, 0.8, 0.1, 0), "reuse", solution="Cannot send because the mailbox is full"),
    Template("Email", "email_access_failure", 1.2, ["Shared mailbox not visible in Outlook", "Need access to shared mailbox"],
             ["I was given access to the procurement shared mailbox yesterday but it does not show in Outlook.",
              "The customer-escalations mailbox disappeared from my Outlook."],
             (0.3, 0.7, 0, 0), "kb", kb="Shared mailbox or team calendar is missing or out of date",
             fixes=["Mailbox permission was granted without auto-mapping; re-applied it and the mailbox appeared."]),
    # ---------------- Printer ----------------
    Template("Printer", "printer_not_printing", 4, ["Print jobs stuck in queue", "Nothing prints at Secure Print"],
             ["My print jobs stay in the queue with error printing and nothing shows when I tap my badge.",
              "Printing a PDF from Acrobat never arrives at the printer on floor {floor}."],
             (0.4, 0.6, 0, 0), "reuse", solution="Secure Print jobs stuck in the laptop queue",
             fixes=["Printer firmware had hung; Print Services restarted the device and cleared its job store."]),
    Template("Printer", "printer_driver", 2, ["Printer missing on new laptop", "Secure Print shows offline"],
             ["Acme Secure Print isn't in my printer list on the new laptop.",
              "The printer shows offline whenever I try to print from home over VPN."],
             (0.5, 0.5, 0, 0), "reuse", solution="Acme Secure Print missing or offline on a laptop"),
    Template("Printer", "printer_not_printing", 1.5, ["Scans not arriving by email", "Scan to Me not working"],
             ["The scanner says sent but the scan never reaches my inbox.",
              "Scanned invoices from the MFP on floor {floor} are not arriving."],
             (0.5, 0.5, 0, 0), "reuse", solution="Scans from the multifunction device never arrive by email"),
    Template("Printer", "paper_jam", 1.8, ["Paper jam on floor printer", "Prints coming out faded with streaks"],
             ["Printer {printer} shows a jam in tray 2 that won't clear.",
              "Every page from {printer} has vertical streaks and faded areas."],
             (0.6, 0.4, 0, 0), "kb", kb="Paper jams, streaks or faded prints",
             fixes=["Fuser unit worn out; Print Services replaced it and ran a calibration."]),
    # ---------------- Hardware ----------------
    Template("Hardware", "battery_issue", 2, ["Laptop will not turn on", "Laptop not charging on dock"],
             ["My laptop won't turn on this morning, no lights at all.",
              "Battery says plugged in, not charging when I use the dock."],
             (0.05, 0.75, 0.2, 0), "reuse", solution="Laptop dead after being left on a dock over the weekend",
             fixes=["Charger was faulty; Hardware Support swapped the adapter at the service desk."]),
    Template("Hardware", "peripheral_issue", 3, ["External monitors show no signal", "Second screen not detected"],
             ["Both monitors on my dock say no signal after lunch, laptop screen works.",
              "The second monitor isn't detected anymore at my desk."],
             (0.3, 0.7, 0, 0), "reuse", solution="External monitors show no signal through the dock",
             fixes=["Dock had failed; Hardware Support replaced the Dell WD19S dock."]),
    Template("Hardware", "peripheral_issue", 1.5, ["Wireless keyboard and mouse stop responding", "Mouse stops working randomly"],
             ["My wireless keyboard and mouse stop working every few minutes.",
              "The mouse freezes randomly and comes back after a while."],
             (0.6, 0.4, 0, 0), "reuse", solution="Wireless keyboard and mouse stop responding"),
    Template("Hardware", "laptop_hardware_failure", 2, ["Laptop overheating and loud fan", "Blue screen twice today"],
             ["The laptop fan is very loud and the base gets hot, then it shuts down.",
              "Got a blue screen with DRIVER_POWER_STATE_FAILURE twice today."],
             (0.05, 0.6, 0.35, 0), "kb", kb="Laptop overheats, fan is loud or the screen turns blue",
             fixes=["Thermal paste dried out; Hardware Support serviced the cooling assembly and updated BIOS.",
                    "Faulty memory module; replaced RAM and ran a 4-hour diagnostic."]),
    Template("Hardware", "display_issue", 1, ["Laptop screen cracked", "Screen damaged after a fall"],
             ["I dropped my laptop and the screen is cracked in the corner.",
              "Coffee spilled near the keyboard and now the screen flickers."],
             (0, 0.4, 0.6, 0), "policy",
             fixes=["Screen and keyboard replaced under the accidental damage cover; loan laptop issued meanwhile."]),
    # ---------------- Software ----------------
    Template("Software", "software_install_request", 4, ["Need Power BI Desktop installed", "Request for AutoCAD licence",
             "Install Python for data work"],
             ["I need Power BI Desktop for the quarterly dashboard, the installer asks for admin rights.",
              "Can you install {app} on my laptop? Needed for a customer project.",
              "Requesting {app} for the new reporting work, my manager has approved."],
             (0.4, 0.6, 0, 0), "reuse", solution="Installer asks for an administrator password",
             fixes=["Packaged and assigned the application in the Company Portal after licence approval."]),
    Template("Software", "license_activation", 2.5, ["Excel says unlicensed product", "Acrobat asking for a trial"],
             ["Word and Excel open read-only with an unlicensed product bar.",
              "Acrobat Pro keeps asking me to start a free trial."],
             (0.1, 0.8, 0.1, 0), "reuse", solution="Excel shows unlicensed product after a team move",
             fixes=["Licence was removed during a team transfer; reassigned the Microsoft 365 licence."]),
    Template("Software", "software_crash", 2.5, ["Power BI Desktop crashes on start", "SAP GUI closes after update"],
             ["{app} closes right after the splash screen since last night's update.",
              "{app} crashes every time I open a saved file."],
             (0.1, 0.7, 0.2, 0), "reuse", solution="Desktop application closes after the splash screen following an update",
             fixes=["Update package was incomplete; Software Support pushed the corrected version to the team."]),
    Template("Software", "software_crash", 2, ["ERP web keeps asking me to sign in", "HR portal sign-in loop"],
             ["The ERP web portal sends me back to the sign-in page every time I log in.",
              "The HR portal keeps reloading the login page, works in a private window."],
             (0.1, 0.8, 0.1, 0), "reuse", solution="Acme ERP web keeps returning to the sign-in page"),
    Template("Software", "software_install_request", 1.5, ["Windows update keeps failing", "Device shows not compliant"],
             ["Windows update fails every night and the Company Portal says I'm not compliant.",
              "Lost access to email on my laptop, Company Portal says update required."],
             (0.1, 0.7, 0.2, 0), "reuse", solution="Windows update fails repeatedly and the device turns non-compliant"),
    # ---------------- Security ----------------
    Template("Security", "phishing_report", 2.5, ["Suspicious invoice email", "Possible phishing message"],
             ["Got an unexpected invoice email from a supplier I don't recognise, didn't open the attachment.",
              "An email asks me to re-activate MFA from an outside address. I haven't clicked anything."],
             (0.1, 0.6, 0.3, 0), "reuse", solution="Reporting a suspicious email that was not opened"),
    Template("Security", "phishing_report", 1, ["Clicked a link in a phishing email", "Entered password on fake page"],
             ["I clicked the link in a delivery email and typed my password before I noticed the address.",
              "Opened an attachment from an unknown sender and enabled editing."],
             (0, 0, 0.6, 0.4), "policy",
             fixes=["Password reset, sessions revoked and mailbox rules checked; no unauthorised access found."]),
    Template("Security", "malware_suspected", 0.8, ["Antivirus alert on laptop", "Strange pop-ups in browser"],
             ["Windows Security says threats found and asks for action.",
              "Browser opens pop-ups on its own and my home page changed."],
             (0, 0.2, 0.6, 0.2), "policy",
             fixes=["Defender quarantined an adware bundle; device scanned clean and browser reset."]),
    Template("Security", "unauthorized_access", 0.6, ["Sign-in alert from unknown location", "Unknown sign-in on my account"],
             ["I received a sign-in alert from a city I have never been to.",
              "Authenticator asked me to approve a sign-in I didn't start."],
             (0, 0, 0.5, 0.5), "policy",
             fixes=["Credential stuffing attempt blocked by conditional access; password reset as a precaution."]),
    # ---------------- Server ----------------
    Template("Server", "server_outage", 1.6, ["HR portal showing 503", "ERP web returns bad gateway"],
             ["The HR portal shows 503 service unavailable for our whole team.",
              "ERP web gives 502 bad gateway since 10 minutes."],
             (0, 0.2, 0.5, 0.3), "policy",
             fixes=["Application pool crashed after a memory leak; restarted and patched the application."]),
    Template("Server", "disk_space", 1.2, ["Disk space alert on reporting server", "Uploads failing, disk full"],
             ["Getting Zabbix alerts that drive D on the reporting server is below 10%.",
              "Uploads to the quality portal fail with no space left on device."],
             (0, 0.3, 0.6, 0.1), "human",
             fixes=["Archived old exports and extended the volume by 200 GB."]),
    Template("Server", "server_performance", 1, ["ERP very slow for the team", "Access denied on team share"],
             ["ERP screens take 30 seconds to load for everyone in procurement.",
              "After moving teams I get access denied on the finance share."],
             (0.1, 0.5, 0.4, 0), "kb", kb="Internal application is very slow for everyone",
             fixes=["Long-running report blocked the application server; tuned the report and added a schedule window.",
                    "Added the user to the finance share access group after data owner approval."]),
    # ---------------- Database ----------------
    Template("Database", "database_access", 2, ["Cannot connect to reporting database", "Login failed on analytics database"],
             ["SSMS can't connect to the reporting database from home, network-related error.",
              "Login failed for user when I connect DBeaver to the analytics database."],
             (0.1, 0.7, 0.2, 0), "reuse", solution="Cannot connect to the ERP reporting replica from home",
             fixes=["Granted reporting database access after manager approval."]),
    Template("Database", "database_performance", 1.6, ["Report query timing out", "Dashboard refresh fails"],
             ["The sales report query times out in the morning.",
              "Power BI refresh fails with a timeout from the reporting database."],
             (0.1, 0.5, 0.4, 0), "reuse", solution="Morning reports time out on the reporting database",
             fixes=["Added an index for the report's date filter; runtime dropped from 4 minutes to 6 seconds."]),
    Template("Database", "database_access", 1.2, ["Permission denied on finance schema", "Need access to payroll tables"],
             ["SELECT permission denied on the finance schema for my analysis.",
              "I need read access to payroll tables for the audit request."],
             (0.2, 0.8, 0, 0), "human",
             fixes=["Read access granted to the schema after data owner approval."]),
]

APPS = ["Power BI Desktop", "AutoCAD 2026", "Python 3.12", "SAP GUI", "Tally Prime", "MATLAB", "Visio"]
PRINTERS = ["PUN-3F-MFP01", "PUN-4F-MFP02", "BLR-2F-MFP01", "CHN-ADM-MFP01"]

# day-of-week load (Mon..Sun) and IST arrival hours: Monday spikes, quiet weekends, morning and post-lunch peaks
WEEKDAY_LOAD = [1.55, 1.15, 1.0, 0.95, 0.8, 0.12, 0.06]
HOURS = [(8, 3), (9, 12), (10, 17), (11, 14), (12, 9), (13, 6), (14, 12), (15, 11), (16, 8), (17, 5), (18, 2), (19, 1)]
BASE_PER_DAY = 3.2
SLA_BREACH_RATE = {"critical": 0.12, "high": 0.12, "medium": 0.1, "low": 0.07}
# What an engineer typically did when the suggested fix was not enough (used when a template lists none)
CATEGORY_FIX = {
    "VPN": "Reset the user's VPN profile on the gateway and confirmed a stable tunnel on a call.",
    "Network": "Checked the switch port and DHCP lease; renewed the lease and confirmed connectivity.",
    "Password": "Verified identity on a video call, cleared the stale credential and confirmed sign-in.",
    "Email": "Recreated the Outlook profile remotely and confirmed mail flow both ways.",
    "Printer": "Reinstalled the Secure Print queue on the laptop and released a test page.",
    "Hardware": "Swapped the faulty part at the service desk and returned the laptop the same day.",
    "Software": "Repaired the installation from the Company Portal and confirmed the app starts.",
    "Security": "Investigated sign-in logs, reset credentials and closed the case with no data exposure.",
    "Server": "Restarted the affected service and added monitoring for the failure condition.",
    "Database": "Adjusted access and checked the query plan; report now completes normally.",
}


@dataclass
class IncidentSpec:
    number: str
    category: str
    intent: str
    title: str
    days_ago: int
    start_ist: tuple[int, int]
    minutes: int
    reports: list[str]
    tickets: int
    root_cause: str
    resolution: str
    priority: str = "high"


INCIDENTS = [
    IncidentSpec("INCIDENT-EMAIL-001", "Email", "email_access_failure", "Outlook disconnected for Pune HQ users",
                 62, (10, 5), 95,
                 ["Outlook says disconnected and I can't open my mailbox.", "Email stopped working for me, Outlook is offline.",
                  "No new emails since 10 am, Outlook keeps trying to connect.", "Can't access my mailbox, web mail is also slow."],
                 14, "A conditional access policy change blocked the Outlook desktop client for one office's network range.",
                 "Rolled back conditional access policy CA-017; Outlook clients reconnected without any action from users.",
                 "critical"),
    IncidentSpec("INCIDENT-VPN-001", "VPN", "vpn_connection_failure", "GlobalProtect gateway unreachable for remote staff",
                 38, (9, 10), 75,
                 ["GlobalProtect can't reach the gateway from home this morning.", "VPN will not connect at all, portal not responding.",
                  "Remote working: the VPN times out connecting to the gateway.", "Cannot connect to VPN since 9 am, tried two networks."],
                 18, "Renewed gateway certificate was installed on only one of the two firewall nodes; the other rejected TLS.",
                 "Installed the certificate on both nodes and failed traffic back; remote sessions restored at 10:25 IST."),
    IncidentSpec("INCIDENT-PRINTER-001", "Printer", "printer_not_printing", "Secure Print release failing at Pune HQ",
                 21, (14, 20), 60,
                 ["Badge release isn't showing any of my jobs.", "Secure Print says no jobs found at every printer on our floor.",
                  "Can't release prints, the printer says server unavailable."],
                 9, "The print server's service account password expired overnight.",
                 "Converted the service account to a managed account and restarted the print queue service."),
    IncidentSpec("INCIDENT-NETWORK-001", "Network", "wifi_connectivity", "ACME-CORP Wi-Fi authentication failing in Bengaluru",
                 8, (9, 40), 50,
                 ["Wi-Fi in the Bengaluru office won't connect this morning.", "Laptop can't join ACME-CORP at the Bengaluru office.",
                  "Office Wi-Fi keeps failing to authenticate on the second floor."],
                 7, "The RADIUS server certificate used for Wi-Fi sign-in expired at 09:30 IST.",
                 "Issued and bound a new RADIUS certificate; devices reconnected automatically within five minutes."),
]


# ------------------------------------------------------------------ helpers
def _username(full_name: str) -> str:
    return ".".join(full_name.lower().split())


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _ist_to_utc(day: date, hour: int, minute: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST).astimezone(timezone.utc)


def _pick(rng: random.Random, weights: tuple[float, ...], values: tuple[str, ...] = ("low", "medium", "high", "critical")) -> str:
    return rng.choices(values, weights=weights)[0]


def _poisson(rng: random.Random, lam: float) -> int:
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def _sla_minutes(priority: str) -> int:
    return get_settings().sla_minutes.get(priority, 480)


def _human_minutes(rng: random.Random, priority: str) -> float:
    target = _sla_minutes(priority)
    if rng.random() < SLA_BREACH_RATE.get(priority, 0.1):
        return target * rng.uniform(1.05, 1.9)
    return target * rng.uniform(0.12, 0.92)


def _progress(outcome: str) -> dict:
    done = {k: "done" for k, _ in PROGRESS_STEPS}
    if outcome in ("policy", "duplicate", "incident"):
        done["troubleshoot"] = "skipped"
        done["verify"] = "skipped"
    if outcome == "verify":
        done["verify"], done["outcome"] = "running", "pending"
    return done


def _candidate(sol: Optional[TicketSolution], doc_title: Optional[str], label: str, similarity: float) -> dict:
    steps = list(sol.steps) if sol else []
    return {
        "kind": "solution" if sol else "kb_procedure", "label": label, "title": sol.title if sol else (doc_title or ""),
        "summary": sol.solution_description if sol else "Documented procedure from the IT knowledge base.",
        "steps": steps, "routing_level": "L3_verified_retrieval", "confidence": round(similarity, 3),
        "solution_id": sol.id if sol else None, "source_ticket": None, "sources": [f"SOL-{sol.id}"] if sol else [],
        "automated_actions": list(sol.automated_actions or []) if sol else [], "similarity": round(similarity, 3),
        "model": None, "safety_flags": [],
    }


# ------------------------------------------------------------------ seeding
class DemoBuilder:
    def __init__(self, db: AsyncSession, ref: dict, now: datetime):
        self.db, self.now = db, now
        self.rng = random.Random(RNG_SEED)
        self.cats: dict[str, TicketCategory] = ref["categories"]
        self.depts: dict[str, Department] = dict(ref["departments"])
        self.users: dict[str, User] = dict(ref["users"])
        self.counts: dict[str, int] = {}
        self.solutions: dict[str, TicketSolution] = {}
        self.docs: dict[str, int] = {}
        self.staff_by_dept: dict[int, list[User]] = {}
        self.employees: list[User] = []
        self.employee_weights: list[float] = []
        self.kb_steps: dict[str, list[str]] = {}
        self.pending_duplicate_notes: list[tuple[Ticket, Ticket]] = []
        self._rr: dict[int, int] = {}

    def count(self, key: str, n: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + n

    # ---------------- people
    async def people(self) -> None:
        roles = {r.name: r for r in (await self.db.execute(select(Role))).scalars()}
        for name, code in BUSINESS_UNITS:
            d = (await self.db.execute(select(Department).where(Department.code == code))).scalar_one_or_none()
            if d is None:
                d = Department(name=name, code=code, description="Business unit", is_support_team=False)
                self.db.add(d)
            self.depts[code] = d
        await self.db.flush()
        pw = hash_password(DEMO_PASSWORD)
        staff_pw = hash_password("Support@123")
        admin_pw = hash_password("Admin@123")
        rows = [(u, n, r, d, t, loc, admin_pw if r == "admin" else staff_pw) for u, n, r, d, t, loc in STAFF]
        rows += [(_username(n), n, "employee", d, t, loc, pw) for n, d, t, loc in EMPLOYEES]
        rows.append((_username(LEAVER[0]), LEAVER[0], "employee", LEAVER[1], LEAVER[2], LEAVER[3], pw))
        for username, full, role, dept, title, loc, hashed in rows:
            u = (await self.db.execute(select(User).where(User.username == username))).unique().scalar_one_or_none()
            if u is None:
                u = User(username=username, email=f"{username}@{DOMAIN}", full_name=full, role=roles[role],
                         department=self.depts[dept], job_title=title, location=loc, password_hash=hashed,
                         created_at=self.now - timedelta(days=self.rng.randint(120, 900)))
                self.db.add(u)
                self.count("users_added")
            self.users[username] = u
        await self.db.flush()
        leaver = self.users[_username(LEAVER[0])]
        leaver.is_active = False
        for u in self.users.values():
            if u.is_active:
                u.last_login_at = self.now - timedelta(hours=self.rng.randint(1, 24 * 6))
            if u.role_name in ("it_support", "admin") and u.department_id:
                self.staff_by_dept.setdefault(u.department_id, []).append(u)
        self.employees = [u for u in self.users.values() if u.role_name == "employee" and u.is_active]
        # some people raise far more tickets than others
        self.employee_weights = [self.rng.choice((0.4, 1, 1, 1.6, 2.5)) for _ in self.employees]

    async def knowledge(self) -> None:
        from app.models import KnowledgeDocument

        for s in (await self.db.execute(select(TicketSolution))).unique().scalars():
            self.solutions.setdefault(s.title, s)
        for d in (await self.db.execute(select(KnowledgeDocument))).unique().scalars():
            self.docs[d.title] = d.id
            procedure = next((c for h, c in chunk_markdown(d.content) if is_procedure(h, c)), "")
            self.kb_steps[d.title] = steps_from_text(procedure)

    def engineer(self, category: str) -> Optional[User]:
        dept_id = self.cats[category].department_id
        team = sorted(self.staff_by_dept.get(dept_id, []), key=lambda u: u.id)
        if not team:
            team = sorted(self.staff_by_dept.get(self.depts["SERVICE_DESK"].id, []), key=lambda u: u.id)
        if not team:
            return None
        i = self._rr.get(dept_id, 0)
        self._rr[dept_id] = i + 1
        return team[i % len(team)]

    def employee(self, *, allow_reference: bool = True, exclude: Optional[set[int]] = None) -> User:
        for _ in range(50):
            u = self.rng.choices(self.employees, weights=self.employee_weights)[0]
            if (allow_reference or u.username not in REFERENCE_EMPLOYEES) and (not exclude or u.id not in exclude):
                return u
        return self.employees[0]

    # ---------------- ticket timeline
    def schedule(self) -> list[datetime]:
        today_ist = self.now.astimezone(IST).date()
        times = []
        for back in range(QUARTER_DAYS, 0, -1):
            day = today_ist - timedelta(days=back)
            for _ in range(_poisson(self.rng, BASE_PER_DAY * WEEKDAY_LOAD[day.weekday()])):
                hour = self.rng.choices([h for h, _ in HOURS], weights=[w for _, w in HOURS])[0]
                times.append(_ist_to_utc(day, hour, self.rng.randint(0, 59)))
        return sorted(times)

    def recent_cutoff(self) -> datetime:
        """Start of the third most recent working day (IST): tickets after it may still be open."""
        day, working = self.now.astimezone(IST).date(), 0
        while working < 3:
            day -= timedelta(days=1)
            working += day.weekday() < 5
        return _ist_to_utc(day, 0, 0)

    async def tickets(self) -> None:
        templates = TEMPLATES
        weights = [t.weight for t in templates]
        last_by_user: dict[int, tuple[Ticket, Template]] = {}
        people = {u.id: u for u in self.employees}
        cutoff = self.recent_cutoff()
        for created in self.schedule():
            tpl = self.rng.choices(templates, weights=weights)[0]
            recent = created >= cutoff
            user = self.employee(allow_reference=not recent)
            prev = last_by_user.get(user.id)
            # same person reporting the same problem again within a few hours -> duplicate of the first ticket
            if (prev and prev[1] is tpl and (created - _aware(prev[0].created_at)).total_seconds() < 6 * 3600
                    and self.rng.random() < 0.8):
                await self.duplicate(prev[0], tpl, user, created)
                continue
            t = await self.ticket(tpl, user, created, recent=recent)
            last_by_user[user.id] = (t, tpl)
        # a few same-day repeat reports, as employees do when something is still broken
        singles = [(t, tpl) for t, tpl in last_by_user.values() if t.status == TicketStatus.RESOLVED]
        for t, tpl in self.rng.sample(singles, min(12, len(singles))):
            again = _aware(t.created_at) + timedelta(minutes=self.rng.randint(25, 160))
            if again < self.now - timedelta(hours=3):
                await self.duplicate(t, tpl, people[t.user_id], again)

    def text(self, tpl: Template, user: User) -> tuple[str, str]:
        title = self.rng.choice(tpl.titles)
        report = self.rng.choice(tpl.reports).format(
            site=user.location or "the office", floor=self.rng.randint(2, 6), desk=f"{self.rng.randint(2, 6)}F-B-{self.rng.randint(101, 140)}",
            printer=self.rng.choice(PRINTERS), app=self.rng.choice(APPS))
        return title, report

    def base_ticket(self, tpl: Template, user: User, created: datetime, title: str, report: str) -> Ticket:
        priority = _pick(self.rng, tpl.priority)
        user_priority = None
        if self.rng.random() < 0.18:  # some employees pick a priority; a few inflate it
            user_priority = _pick(self.rng, (0.1, 0.4, 0.4, 0.1))
        cat = self.cats[tpl.category]
        scope = "Single user affected" if priority in ("low", "medium") else "Blocks the user's work"
        return Ticket(
            ticket_number=f"TMP-{self.rng.getrandbits(48):x}", user_id=user.id, title=title, description=report,
            category_id=cat.id, sub_category=INTENT_LABELS.get(tpl.intent), intent=tpl.intent, entities={},
            ai_confidence=round(self.rng.uniform(0.72, 0.97), 3), classification_method="rules",
            user_priority=user_priority, system_priority=priority, priority=priority,
            priority_confidence=round(self.rng.uniform(0.6, 0.9), 2),
            priority_reason=f"{scope}; category {tpl.category}", priority_impact=scope, priority_urgency="Standard",
            status=TicketStatus.NEW, source=self.rng.choices(["ai_chatbot", "portal"], weights=[0.86, 0.14])[0],
            extra_data={"demo": True}, created_at=created, updated_at=created,
        )

    async def open_now(self) -> None:
        """Work that is visibly in flight at demo time: fixes waiting for the employee's approval today, and older
        tickets parked with an engineer (parts on order, licence purchase) that have run past their SLA."""
        waiting = [("GlobalProtect keeps dropping and reconnecting from home", 3.5),
                   ("Outlook closes on start after the monthly Office update", 6),
                   ("Secure Print jobs stuck in the laptop queue", 14)]
        for title, hours in waiting:
            tpl = next(t for t in TEMPLATES if t.solution == title)
            user = self.employee(allow_reference=False)
            t_title, report = self.text(tpl, user)
            t = self.base_ticket(tpl, user, self.now - timedelta(hours=hours), t_title, report)
            await self.write(t, tpl, user, "ai", "verify", self.solutions.get(title))
        parked = [("Laptop overheats, fan is loud or the screen turns blue", 9,
                   "Replacement fan assembly ordered from the vendor; expected in 2 working days. Loan laptop issued."),
                  ("Installer asks for an administrator password", 6,
                   "Waiting for the AutoCAD licence purchase order to be approved by Procurement."),
                  ("Permission denied on finance schema", 4, "Waiting for the finance data owner to approve read access."),
                  ("Network is slow when opening files or loading internal apps", 5,
                   "Uplink upgrade for floor 4 scheduled for Saturday's maintenance window.")]
        for key, days, note in parked:
            tpl = next(t for t in TEMPLATES if key in (t.kb, t.solution) or key in t.titles)
            user = self.employee(allow_reference=False)
            t_title, report = self.text(tpl, user)
            created = self.now - timedelta(days=days, hours=self.rng.uniform(0, 6))
            t = self.base_ticket(tpl, user, created, t_title, report)
            t.priority = t.system_priority = "medium"
            await self.write(t, tpl, user, "human", "in_progress", None)
            engineer_id = t.assigned_to
            self.db.add(TicketMessage(ticket_id=t.id, user_id=engineer_id, role="agent", is_internal=True,
                                      content=note, created_at=created + timedelta(days=1)))
            self.db.add(TicketMessage(ticket_id=t.id, user_id=engineer_id, role="agent",
                                      content="Update: " + note.split(";")[0], created_at=created + timedelta(days=1, minutes=5)))
            self.count("parked_open")

    async def ticket(self, tpl: Template, user: User, created: datetime, *, recent: bool) -> Ticket:
        title, report = self.text(tpl, user)
        t = self.base_ticket(tpl, user, created, title, report)
        sol = self.solutions.get(tpl.solution) if tpl.solution else None
        roll = self.rng.random()
        path = tpl.path
        if path == "reuse" and sol is None:
            path = "kb" if tpl.kb else "human"
        if path == "policy" or t.priority == "critical":
            outcome = "policy"
        elif path == "human":
            outcome = "human"
        elif path == "reuse":
            outcome = "ai" if roll < 0.72 else ("tried_then_human" if roll < 0.95 else "closed")
        else:
            outcome = "ai_kb" if roll < 0.45 else ("tried_then_human" if roll < 0.95 else "closed")
        open_state = None
        if recent:
            if outcome in ("ai", "ai_kb") and self.rng.random() < 0.35:
                open_state = "verify"
            elif outcome in ("policy", "human", "tried_then_human") and self.rng.random() < 0.7:
                open_state = self.rng.choice(["escalated", "assigned", "in_progress", "in_progress"])
        await self.write(t, tpl, user, outcome, open_state, sol)
        return t

    async def write(self, t: Ticket, tpl: Template, user: User, outcome: str, open_state: Optional[str],
                    sol: Optional[TicketSolution]) -> None:
        created = _aware(t.created_at)
        rng = self.rng
        cat = self.cats[tpl.category]
        dept_id = cat.department_id
        engineer = None
        resolved_at = None
        if outcome in ("ai", "ai_kb"):
            resolved_at = created + timedelta(minutes=rng.uniform(4, 38))
        elif outcome == "closed":
            resolved_at = created + timedelta(days=rng.uniform(3, 5))
        elif outcome in ("policy", "human", "tried_then_human"):
            resolved_at = created + timedelta(minutes=_human_minutes(rng, t.priority) + (25 if outcome == "tried_then_human" else 0))
        if open_state or (resolved_at and resolved_at > self.now - timedelta(minutes=20)):
            resolved_at = None
            open_state = open_state or ("verify" if outcome in ("ai", "ai_kb") else "in_progress")

        escalated = outcome in ("policy", "human", "tried_then_human")
        if escalated:
            engineer = self.engineer(tpl.category)
            t.department_id = dept_id
            if open_state != "escalated":
                t.assigned_to = engineer.id if engineer else None
        if open_state == "verify":
            t.status = TicketStatus.AWAITING_USER
        elif open_state:
            t.status = {"escalated": TicketStatus.ESCALATED, "assigned": TicketStatus.ASSIGNED,
                        "in_progress": TicketStatus.IN_PROGRESS}[open_state]
        elif outcome == "closed":
            t.status = TicketStatus.CLOSED
        else:
            t.status = TicketStatus.RESOLVED
        t.resolved_at = resolved_at
        fix = rng.choice(tpl.fixes) if tpl.fixes else CATEGORY_FIX[tpl.category]
        label = "VERIFIED SOLUTION" if sol and sol.confidence_level == SolutionConfidence.ADMIN_VERIFIED else "HUMAN-APPROVED SOLUTION"
        if outcome == "ai" and not open_state:
            t.resolved_by_ai = True
            t.resolution_summary = f"{label}: {sol.title}"
        elif outcome == "ai_kb" and not open_state:
            t.resolved_by_ai = True
            t.resolution_summary = f"VERIFIED SOLUTION: {tpl.kb}"
        elif outcome == "closed":
            t.resolution_summary = "Closed: no reply from the employee after the suggested fix (auto-closed after 3 days)."
        elif escalated and not open_state:
            t.resolution_summary = fix or "Resolved by IT support."
        t.updated_at = resolved_at or created + timedelta(minutes=rng.uniform(3, 90))
        self.db.add(t)
        await self.db.flush()
        self.count("tickets")

        # ---- agent run, steps, messages, events
        similarity = rng.uniform(0.68, 0.91)
        if outcome == "policy":
            routing, run_state, resolution = "L0_policy", "escalated", "escalated"
        elif outcome == "human":
            routing, run_state, resolution = "L1_rules", "escalated", "escalated"
        elif outcome == "tried_then_human":
            routing, run_state, resolution = "L3_verified_retrieval", "escalated", "escalated"
        elif open_state == "verify":
            routing, run_state, resolution = "L3_verified_retrieval", "verify", None
        else:
            routing, run_state, resolution = "L3_verified_retrieval", "resolved" if outcome != "closed" else "closed", \
                "resolved" if outcome != "closed" else "human_takeover"
        decisions = [f"Classified as {tpl.category}/{tpl.intent} via rules", f"Retrieved {rng.randint(2, 6)} knowledge hit(s)"]
        tried = []
        if outcome in ("ai", "tried_then_human", "closed") and sol:
            decisions.append(f"Reusing {sol.confidence_level} solution SOL-{sol.id} ({similarity:.2f}) without LLM")
        elif outcome in ("ai_kb",) or (outcome == "tried_then_human" and not sol):
            decisions.append("Presenting documented procedure from the knowledge base")
        if outcome == "tried_then_human":
            decisions.append("Attempt 1 did not resolve the issue")
            tried.append({"title": sol.title if sol else tpl.kb, "label": label, "steps": list(sol.steps)[:4] if sol else []})
        if outcome == "policy":
            decisions.append("Policy: routed to the owning team without automated troubleshooting")
        ctx = {"progress": _progress("verify" if open_state == "verify" else ("policy" if outcome == "policy" else "done")),
               "decisions": decisions, "tried": tried,
               "retrieval": [{"type": "solution", "id": sol.id, "title": sol.title, "similarity": round(similarity, 3),
                              "confidence_level": sol.confidence_level, "source_ticket": None}] if sol else []}
        if routing == "L3_verified_retrieval":
            ctx["llm_skipped"] = True
        if open_state == "verify":
            ctx["current"] = {**_candidate(sol, tpl.kb, label if sol else "VERIFIED SOLUTION", similarity),
                              **({} if sol else {"steps": self.kb_steps.get(tpl.kb or "", [])})}
        finished = None if open_state == "verify" or (escalated and open_state) else \
            created + timedelta(minutes=rng.uniform(0.5, 3) if outcome == "policy" else rng.uniform(2, 30))
        run = AgentRun(ticket_id=t.id, state=run_state, attempt=1 if outcome == "tried_then_human" else 0, context=ctx,
                       routing_level=routing, llm_calls=0, tokens_used=0, estimated_cost=0.0,
                       retrieval_hits=0 if outcome == "human" else rng.randint(1, 6), confidence=round(similarity, 3),
                       resolution_status=resolution, reasoning_summary=" | ".join(decisions),
                       escalation_reason=("Security and policy cases go straight to the owning team" if outcome == "policy"
                                          else "No verified solution matched" if outcome == "human"
                                          else "Not resolved after 1 troubleshooting attempt" if outcome == "tried_then_human" else None),
                       started_at=created, completed_at=finished,
                       latency_ms=round(rng.uniform(380, 2400), 1))
        self.db.add(run)
        await self.db.flush()

        at = created
        step = lambda key, title, detail, status="completed", by="agent", minutes=0.2: TroubleshootingStep(  # noqa: E731
            ticket_id=t.id, agent_run_id=run.id, step_key=key, title=title, detail=detail, status=status,
            performed_by=by, created_at=at + timedelta(minutes=minutes))
        self.db.add_all([
            step("understand", "Ticket ingestion", f"Created from {'AI chat' if t.source == 'ai_chatbot' else 'the portal form'}", minutes=0.05),
            step("classify", "Pattern classification", f"{tpl.category} / {t.sub_category} ({(t.ai_confidence or 0) * 100:.0f}% confidence, rules); priority {t.priority.upper()}", minutes=0.08),
            step("check_duplicate", "Duplicate & incident check", "No duplicate or active incident found", minutes=0.12),
            step("search_history", "Vector similarity search",
                 f"{1 if sol else 0} known solution(s), {rng.randint(1, 4)} KB section(s)", minutes=0.2),
        ])
        self.db.add(TicketMessage(ticket_id=t.id, user_id=t.user_id, role="user", content=t.description,
                                  payload={}, created_at=created))
        self.db.add(TicketEvent(ticket_id=t.id, user_id=t.user_id, event_type="ticket_created", new_value="ai_analysis",
                                description=f"Ticket created via {t.source}", created_at=created))

        candidate = None
        if outcome in ("ai", "ai_kb", "tried_then_human", "closed"):
            candidate = _candidate(sol, tpl.kb, label if sol else "VERIFIED SOLUTION", similarity)
            if not sol:
                candidate["steps"] = self.kb_steps.get(tpl.kb or "", [])
        if candidate:
            self.db.add(step("troubleshoot", "Remediation retrieved", f"{candidate['label']}: {candidate['title']}", minutes=0.3))
            self.db.add(TicketMessage(
                ticket_id=t.id, role="assistant", created_at=created + timedelta(minutes=0.4),
                content=(f"I found a **{label.lower()}** that matches your issue "
                         f"({similarity * 100:.0f}% match). Please try the steps below, then let me know: "
                         "**did this resolve your issue?**") if sol else
                        "I found the documented procedure for this in the IT knowledge base. Please try the steps below, "
                        "then let me know: **did this resolve your issue?**",
                payload={"solution": candidate, "quick_replies": ["Yes, it's fixed", "No, still not working"]}))
            await self.approvals(t, run, candidate, created, pending=open_state == "verify")

        if open_state == "verify":
            self.db.add(step("verify", "Verification", "Waiting for the employee to confirm whether the fix worked",
                             status="running", by="user", minutes=0.5))
        elif outcome in ("ai", "ai_kb"):
            self.db.add(step("verify", "Verification passed", "Employee confirmed the issue is resolved", by="user",
                             minutes=(resolved_at - created).total_seconds() / 60))
            self.db.add(TicketMessage(ticket_id=t.id, user_id=t.user_id, role="user", content="Yes, it's fixed",
                                      created_at=resolved_at))
            self.db.add(TicketEvent(ticket_id=t.id, user_id=t.user_id, event_type="status_changed", old_value="awaiting_user",
                                    new_value="resolved", description="Employee confirmed the AI-proposed fix worked",
                                    created_at=resolved_at))
            await self.feedback(t, sol, True, resolved_at, rating=rng.choices([5, 4, 3], weights=[62, 31, 7])[0])
            if sol:
                sol.times_used = (sol.times_used or 0) + 1
                sol.times_successful = (sol.times_successful or 0) + 1
            elif rng.random() < 0.6:
                await self.capture(t, tpl, SolutionConfidence.USER_CONFIRMED, resolved_at, None)
        elif outcome == "closed":
            self.db.add(TicketEvent(ticket_id=t.id, event_type="status_changed", old_value="awaiting_user", new_value="closed",
                                    description="Auto-closed: no reply from the employee for 3 days", created_at=resolved_at))

        if escalated:
            await self.escalation(t, tpl, user, run, engineer, created, open_state, resolved_at, outcome, fix)

    async def approvals(self, t: Ticket, run: AgentRun, candidate: dict, created: datetime, *, pending: bool) -> None:
        for name in candidate["automated_actions"]:
            spec = get_tool(name)
            if spec is None:
                continue
            decided = created + timedelta(minutes=self.rng.uniform(1, 6))
            if pending:
                status, result, approved_by, decided_at = "pending_approval", {"summary": "Awaiting approval (restricted)"}, None, None
            else:
                approve = self.rng.random() < 0.86
                status = "approved" if approve else "rejected"
                approved_by, decided_at = t.user_id, decided
                result = ({"ok": True, "mode": "dry_run", "executed": False,
                           "summary": f"{spec.label} approved and queued (dry-run: no endpoint-management connector configured)"}
                          if approve else {"ok": None, "summary": "Rejected by the employee"})
                self.db.add(AuditLog(user_id=t.user_id, action="action_approved" if approve else "action_rejected",
                                     resource_type="agent_action", details={"tool": name, "demo": True}, created_at=decided))
            self.db.add(AgentAction(agent_run_id=run.id, ticket_id=t.id, tool_name=name, permission_level=spec.permission,
                                    parameters={}, result=result, status=status, approval_required=True,
                                    approver_role=spec.approver_role, approved_by=approved_by, decided_at=decided_at,
                                    created_at=created + timedelta(minutes=0.4)))
            self.count("approvals_pending" if pending else "approvals_decided")

    async def feedback(self, t: Ticket, sol: Optional[TicketSolution], resolved: bool, at: datetime, *,
                       rating: Optional[int], comment: Optional[str] = None) -> None:
        self.db.add(TicketFeedback(ticket_id=t.id, user_id=t.user_id, solution_id=sol.id if sol else None,
                                   issue_resolved=resolved, satisfaction_rating=rating, comments=comment, created_at=at))
        self.count("feedback")

    async def escalation(self, t: Ticket, tpl: Template, user: User, run: AgentRun, engineer: Optional[User], created: datetime,
                         open_state: Optional[str], resolved_at: Optional[datetime], outcome: str, fix: Optional[str]) -> None:
        rng = self.rng
        dept = await self.db.get(Department, t.department_id) if t.department_id else None
        esc_at = created + timedelta(minutes=rng.uniform(0.6, 2) if outcome != "tried_then_human" else rng.uniform(15, 40))
        if outcome == "tried_then_human":
            self.db.add(TicketMessage(ticket_id=t.id, user_id=t.user_id, role="user", content="No, still not working",
                                      created_at=esc_at - timedelta(minutes=0.5)))
            await self.feedback(t, None, False, esc_at - timedelta(minutes=0.5), rating=None, comment=None)
        reason = run.escalation_reason or "Escalated to the owning team"
        self.db.add(TicketEscalation(
            ticket_id=t.id, department_id=t.department_id, reason=reason, created_at=esc_at,
            package={"ticket_id": None, "summary": t.title, "description": t.description, "category": tpl.category,
                     "intent": tpl.intent, "priority": t.priority, "user_priority": t.user_priority, "entities": {},
                     "troubleshooting_attempted": (run.context or {}).get("tried", []), "diagnostics": [],
                     "retrieved_solutions": (run.context or {}).get("retrieval", []),
                     "agent_reasoning_summary": run.reasoning_summary,
                     "user_information": {"name": user.full_name,
                                          "department": user.department.name if user.department else None,
                                          "location": user.location},
                     "recommended_department": dept.name if dept else None, "escalation_reason": reason}))
        self.db.add(TroubleshootingStep(ticket_id=t.id, agent_run_id=run.id, step_key="escalate",
                                        title="Escalated to human support",
                                        detail=f"{dept.name if dept else 'IT'}: {reason}", created_at=esc_at))
        self.db.add(TicketEvent(ticket_id=t.id, event_type="escalated", new_value=dept.name if dept else None,
                                description=reason, created_at=esc_at))
        self.db.add(TicketMessage(
            ticket_id=t.id, role="assistant", created_at=esc_at,
            content=f"I've escalated this to the **{dept.name if dept else 'IT'}** team"
                    + (f" and assigned it to {engineer.full_name}" if engineer and open_state != "escalated" else "")
                    + f". Reason: {reason}. They'll receive everything we've tried so far.",
            payload={"escalation": {"department": dept.name if dept else None, "reason": reason,
                                    "assignee": engineer.full_name if engineer and open_state != "escalated" else None}}))
        if engineer and open_state != "escalated":
            assigned_at = esc_at + timedelta(minutes=rng.uniform(0.1, 1))
            self.db.add(TicketAssignment(ticket_id=t.id, assigned_to=engineer.id, reason=f"Auto-assigned on escalation to {dept.name if dept else 'IT'}",
                                         created_at=assigned_at))
            self.db.add(TicketEvent(ticket_id=t.id, event_type="assigned", new_value=engineer.full_name,
                                    description=f"Auto-assigned on escalation to {dept.name if dept else 'IT'}", created_at=assigned_at))
            started = assigned_at + timedelta(minutes=rng.uniform(5, 40))
            if (resolved_at is None or started < resolved_at) and started < self.now:
                self.db.add(TicketEvent(ticket_id=t.id, user_id=engineer.id, event_type="status_changed", old_value="assigned",
                                        new_value="in_progress", description="Accepted from queue", created_at=started))
                if rng.random() < 0.5:
                    self.db.add(TicketMessage(ticket_id=t.id, user_id=engineer.id, role="agent", created_at=started + timedelta(minutes=2),
                                              content=rng.choice(["Looking into this now.", "I'm on it - will update you shortly.",
                                                                  "Picked this up. Are you available for a quick Teams call?"])))
        if resolved_at:
            self.db.add(TroubleshootingStep(ticket_id=t.id, step_key="manual", title="Resolved by IT support",
                                            detail=t.resolution_summary, performed_by="it_support",
                                            created_by=engineer.id if engineer else None, created_at=resolved_at))
            self.db.add(TicketMessage(ticket_id=t.id, user_id=engineer.id if engineer else None, role="agent",
                                      content=f"Resolved: {t.resolution_summary}", created_at=resolved_at))
            self.db.add(TicketEvent(ticket_id=t.id, user_id=engineer.id if engineer else None, event_type="status_changed",
                                    old_value="in_progress", new_value="resolved", description="Resolved by IT support",
                                    created_at=resolved_at))
            if rng.random() < 0.7:
                rating = rng.choices([5, 4, 3, 2], weights=[48, 34, 13, 5])[0]
                await self.feedback(t, None, True, resolved_at + timedelta(hours=rng.uniform(0.2, 6)), rating=rating)
            if fix and rng.random() < 0.18:
                await self.capture(t, tpl, SolutionConfidence.HUMAN_VERIFIED, resolved_at, engineer, fix)

    async def capture(self, t: Ticket, tpl: Template, level: str, at: datetime, engineer: Optional[User],
                      text: Optional[str] = None) -> None:
        """Resolution saved as knowledge, as the support console and the agent do."""
        title = f"{tpl.titles[0]} ({at.astimezone(IST):%d %b})"
        steps = [s.strip() for s in text.split(";") if s.strip()] if text else self.kb_steps.get(tpl.kb or "", [])
        sol = TicketSolution(ticket_id=t.id, category_id=t.category_id, intent=tpl.intent, title=title[:300],
                             problem_description=t.description, solution_description=text or f"Followed: {tpl.kb}",
                             steps=steps, automated_actions=[], confidence_level=level,
                             source="it_support" if level == SolutionConfidence.HUMAN_VERIFIED else "agent",
                             times_used=1, times_successful=1, created_by=engineer.id if engineer else None,
                             verified_by=engineer.id if engineer and level == SolutionConfidence.HUMAN_VERIFIED else None,
                             verified_at=at if level == SolutionConfidence.HUMAN_VERIFIED else None,
                             created_at=at, updated_at=at)
        self.db.add(sol)
        self.count("knowledge_captured")

    async def duplicate(self, original: Ticket, tpl: Template, user: User, created: datetime) -> None:
        title, report = self.text(tpl, user)
        t = self.base_ticket(tpl, user, created, title, report)
        t.status, t.duplicate_of_id = TicketStatus.DUPLICATE, original.id
        t.resolved_at = created + timedelta(minutes=0.5)
        t.priority = original.priority
        t.extra_data = {"demo": True, "duplicate_similarity": round(self.rng.uniform(0.78, 0.93), 3)}
        t.updated_at = t.resolved_at
        self.db.add(t)
        await self.db.flush()
        run = AgentRun(ticket_id=t.id, state="duplicate", context={"progress": _progress("duplicate"), "decisions": [
            "Same-user duplicate detected"]}, routing_level="L2_similarity", resolution_status="duplicate",
            reasoning_summary="Same-user duplicate detected", started_at=created, completed_at=created + timedelta(seconds=20),
            latency_ms=round(self.rng.uniform(200, 600), 1))
        self.db.add(run)
        self.db.add(TicketMessage(ticket_id=t.id, user_id=user.id, role="user", content=t.description, payload={}, created_at=created))
        self.db.add(TicketEvent(ticket_id=t.id, user_id=user.id, event_type="ticket_created", new_value="ai_analysis",
                                description=f"Ticket created via {t.source}", created_at=created))
        self.pending_duplicate_notes.append((t, original))
        self.count("duplicates")

    # ---------------- incidents
    async def incidents(self) -> None:
        today_ist = self.now.astimezone(IST).date()
        for spec in INCIDENTS:
            day = today_ist - timedelta(days=spec.days_ago)
            start = _ist_to_utc(day, *spec.start_ist)
            end = start + timedelta(minutes=spec.minutes)
            cat = self.cats[spec.category]
            exists = (await self.db.execute(select(Incident).where(Incident.incident_number == spec.number))).scalar_one_or_none()
            if exists:
                continue
            inc = Incident(incident_number=spec.number, title=spec.title, category_id=cat.id, priority=spec.priority,
                           status="resolved", department_id=cat.department_id, root_cause=spec.root_cause,
                           resolution=spec.resolution, detection_similarity=round(self.rng.uniform(0.71, 0.84), 3),
                           description=(f"Automatically correlated: {spec.tickets} employees reported semantically similar "
                                        f"{spec.category} issues within {get_settings().INCIDENT_WINDOW_MINUTES} minutes."),
                           first_reported=start, last_reported=start, resolved_at=end, created_at=start)
            self.db.add(inc)
            await self.db.flush()
            engineer = self.engineer(spec.category)
            used: set[int] = set()
            last = start
            for i in range(spec.tickets):
                user = self.employee(exclude=used)
                used.add(user.id)
                created = start + timedelta(minutes=i * spec.minutes * 0.55 / spec.tickets + self.rng.uniform(0, 3))
                last = max(last, created)
                report = self.rng.choice(spec.reports)
                t = Ticket(ticket_number=f"TMP-{self.rng.getrandbits(48):x}", user_id=user.id,
                           title=f"{spec.category} issue: {report.rstrip('.')}"[:120], description=report,
                           category_id=cat.id, sub_category=INTENT_LABELS.get(spec.intent), intent=spec.intent, entities={},
                           ai_confidence=round(self.rng.uniform(0.75, 0.95), 3), classification_method="rules",
                           system_priority="high", priority="high", priority_confidence=0.8,
                           priority_reason="Several users affected", priority_impact="Several users affected",
                           priority_urgency="High", status=TicketStatus.RESOLVED, source="ai_chatbot",
                           department_id=cat.department_id, incident_id=inc.id, resolved_at=end,
                           resolution_summary=f"Resolved with {spec.number}: {spec.resolution}",
                           extra_data={"demo": True}, created_at=created, updated_at=end)
                self.db.add(t)
                await self.db.flush()
                linked_at = created + timedelta(seconds=40)
                self.db.add(AgentRun(ticket_id=t.id, state="linked_incident", context={
                    "progress": _progress("incident"), "decisions": [f"Correlated into {spec.number}"]},
                    routing_level="L2_similarity", resolution_status="linked_incident", retrieval_hits=0,
                    reasoning_summary=f"Correlated into {spec.number}", started_at=created, completed_at=linked_at,
                    latency_ms=round(self.rng.uniform(300, 900), 1)))
                self.db.add_all([
                    TicketMessage(ticket_id=t.id, user_id=user.id, role="user", content=report, payload={}, created_at=created),
                    TicketMessage(ticket_id=t.id, role="assistant", created_at=linked_at, payload={
                        "incident": {"number": spec.number, "title": spec.title, "status": "active"}},
                        content=f"This issue appears to be part of an existing incident, **{spec.number}** - {spec.title}. "
                                "The owning team is working on it, so there's no need for individual troubleshooting."),
                    TicketMessage(ticket_id=t.id, user_id=engineer.id if engineer else None, role="agent", created_at=end,
                                  content=f"{spec.number} has been resolved: {spec.resolution}"),
                    TicketEvent(ticket_id=t.id, user_id=user.id, event_type="ticket_created", new_value="ai_analysis",
                                description="Ticket created via ai_chatbot", created_at=created),
                    TicketEvent(ticket_id=t.id, event_type="linked_to_incident", new_value=spec.number,
                                description=f"Correlated with {spec.number} (similarity {inc.detection_similarity:.2f})",
                                created_at=linked_at),
                    TicketEvent(ticket_id=t.id, user_id=engineer.id if engineer else None, event_type="status_changed",
                                old_value="linked_incident", new_value="resolved", description=f"Resolved via {spec.number}",
                                created_at=end),
                ])
                if self.rng.random() < 0.35:
                    await self.feedback(t, None, True, end + timedelta(hours=self.rng.uniform(0.5, 4)),
                                        rating=self.rng.choices([5, 4, 3], weights=[40, 45, 15])[0])
                self.count("incident_tickets")
            inc.last_reported = last
            self.db.add(TicketSolution(category_id=cat.id, intent=spec.intent, title=spec.title,
                                       problem_description=inc.description, root_cause=spec.root_cause,
                                       solution_description=spec.resolution, steps=[spec.resolution],
                                       confidence_level=SolutionConfidence.HUMAN_VERIFIED, source="it_support",
                                       created_by=engineer.id if engineer else None,
                                       verified_by=engineer.id if engineer else None, verified_at=end,
                                       times_used=0, times_successful=0, created_at=end, updated_at=end,
                                       ticket_id=(await self.db.execute(select(Ticket.id).where(
                                           Ticket.incident_id == inc.id).order_by(Ticket.id).limit(1))).scalar()))
            self.db.add(AuditLog(user_id=engineer.id if engineer else None, action="incident_resolved",
                                 resource_type="incident", resource_id=inc.id,
                                 details={"tickets_closed": spec.tickets, "demo": True}, created_at=end))
            self.count("incidents")

    # ---------------- administration history
    async def admin_history(self) -> None:
        manager = self.users["it.manager"]
        leaver = self.users[_username(LEAVER[0])]
        admin = self.users.get("admin")
        self.db.add_all([
            AuditLog(user_id=admin.id if admin else None, action="role_changed", resource_type="user", resource_id=manager.id,
                     details={"from": "it_support", "to": "admin"}, ip_address="10.20.4.18",
                     created_at=self.now - timedelta(days=74)),
            AuditLog(user_id=manager.id, action="user_deactivated", resource_type="user", resource_id=leaver.id,
                     ip_address="10.20.4.21", created_at=self.now - timedelta(days=19)),
        ])
        for u in self.rng.sample([u for u in self.users.values() if u.is_active], 12):
            self.db.add(AuditLog(user_id=u.id, action="login", resource_type="user", resource_id=u.id,
                                 ip_address=f"10.20.{self.rng.randint(2, 9)}.{self.rng.randint(10, 250)}",
                                 created_at=_aware(u.last_login_at or self.now)))

    # ---------------- finishing
    async def finish(self) -> None:
        await self.db.flush()
        await renumber_tickets(self.db)
        for dup, original in self.pending_duplicate_notes:
            self.db.add(TicketEvent(ticket_id=dup.id, event_type="status_changed", old_value="ai_analysis", new_value="duplicate",
                                    description=f"Duplicate of {original.ticket_number} (same employee, same issue)",
                                    created_at=_aware(dup.created_at) + timedelta(seconds=30)))
            self.db.add(TicketMessage(ticket_id=dup.id, role="assistant", created_at=_aware(dup.created_at) + timedelta(seconds=30),
                                      content=f"It looks like you already reported this issue in **{original.ticket_number}**. "
                                              "I've linked this report to it instead of opening a second ticket.",
                                      payload={"duplicate": {"number": original.ticket_number, "title": original.title}}))
            self.db.add(TicketEvent(ticket_id=original.id, event_type="duplicate_linked", new_value=dup.ticket_number,
                                    description=f"{dup.ticket_number} was reported again by the same user",
                                    created_at=_aware(dup.created_at) + timedelta(seconds=30)))


async def renumber_tickets(db: AsyncSession) -> bool:
    """Give seed tickets chronological numbers (INC-000001 is the oldest). Only the numbers already in use are
    reassigned, so tickets created later continue the sequence without collisions. Skipped when the database
    holds tickets that did not come from a seed."""
    tickets = (await db.execute(select(Ticket).order_by(Ticket.created_at, Ticket.id))).unique().scalars().all()
    if any(t.source not in ("historical_import",) and not (t.extra_data or {}).get("demo") for t in tickets):
        return False
    ids = sorted(t.id for t in tickets)
    for t in tickets:  # two passes: ticket_number is unique
        await db.execute(update(Ticket).where(Ticket.id == t.id)
                         .values(ticket_number=f"TMP-{t.id}", updated_at=Ticket.updated_at)
                         .execution_options(synchronize_session=False))
    numbers = {}
    for t, number_id in zip(tickets, ids):
        numbers[t.id] = f"INC-{number_id:06d}"
        # updated_at=updated_at keeps "last updated" as it was (the column has onupdate=now)
        await db.execute(update(Ticket).where(Ticket.id == t.id)
                         .values(ticket_number=numbers[t.id], updated_at=Ticket.updated_at)
                         .execution_options(synchronize_session=False))
        set_committed_value(t, "ticket_number", numbers[t.id])
    for esc in (await db.execute(select(TicketEscalation))).unique().scalars():
        esc.package = {**(esc.package or {}), "ticket_id": numbers.get(esc.ticket_id)}
    await db.flush()
    return True


async def seed_demo_company(db: AsyncSession, ref: dict, now: Optional[datetime] = None) -> dict:
    """Idempotent: returns {"skipped": True} when the demo company already exists."""
    if (await db.execute(select(func.count(AuditLog.id)).where(AuditLog.action == MARKER))).scalar():
        return {"skipped": True}
    builder = DemoBuilder(db, ref, now or utcnow())
    await builder.people()
    await builder.knowledge()
    await builder.incidents()
    await builder.tickets()
    await builder.open_now()
    await builder.admin_history()
    await builder.finish()
    db.add(AuditLog(action=MARKER, resource_type="seed", details={"company": COMPANY, **builder.counts}))
    await db.flush()
    return builder.counts


def demo_accounts(users: list[User]) -> list[str]:
    """Printable list of demo sign-ins, grouped by role and team."""
    lines = []
    by_role: dict[str, list[User]] = {}
    for u in users:
        if u.is_active:
            by_role.setdefault(u.role_name, []).append(u)
    for role, password in (("admin", "Admin@123"), ("it_support", "Support@123"), ("employee", DEMO_PASSWORD)):
        people = sorted(by_role.get(role, []), key=lambda u: ((u.department.name if u.department else ""), u.username))
        lines.append(f"\n{role.replace('_', ' ').title()} accounts ({len(people)}), password {password}:")
        if role == "employee":
            groups: dict[str, list[str]] = {}
            for u in people:
                groups.setdefault(u.department.name if u.department else "-", []).append(u.username)
            for dept, names in groups.items():
                lines.append(f"  {dept:<24} {', '.join(names)}")
        else:
            for u in people:
                lines.append(f"  {u.username:<14} {u.full_name:<20} {u.department.name if u.department else '-'}")
    return lines
