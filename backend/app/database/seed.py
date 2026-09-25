"""
Precision AI - Seed data (synthetic; no real personal information).

  python -m app.database.seed               # reference data + KB + history + live simulation
  python -m app.database.seed --no-simulate # skip replaying live reports through the agent

Idempotent: reference data is upserted by natural key; tickets are only seeded into an empty DB.
The "live" reports are replayed through the real chat/agent pipeline, so the agent runs, incidents,
duplicates and LLM-usage metrics shown on dashboards are produced by the system itself.
"""

import argparse
import asyncio
import json
import re
from datetime import timedelta

from sqlalchemy import func, select

from app.core.config import PROJECT_DIR, get_settings
from app.core.logging import setup_logging
from app.core.security import hash_password
from app.database import async_session_factory, utcnow
from app.models import (
    Department, KnowledgeDocument, Role, Ticket, TicketCategory, TicketEscalation, TicketStatus, User,
)
from app.services import knowledge, tickets as ticket_svc
from app.services.classification import DEFAULT_KEYWORDS, INTENTS, detect_intent, extract_entities
from app.vector_store import get_index_manager

DATA = PROJECT_DIR / "data"

ROLES = {
    "employee": ("Employee - submits and tracks own tickets", {"tickets": "own"}),
    "it_support": ("IT support agent - manages assigned and escalated tickets", {"tickets": "queue", "knowledge": "curate"}),
    "admin": ("Administrator - full access, analytics and user management", {"all": True}),
}

# (name, code, description, is_support_team)
DEPARTMENTS = [
    ("Service Desk", "SERVICE_DESK", "First-line IT service desk (fallback queue)", True),
    ("Network Team", "NETWORK", "Network, Wi-Fi and VPN infrastructure", True),
    ("Identity & Access Team", "IAM", "Accounts, passwords, MFA and access", True),
    ("Email & Collaboration Team", "EMAIL", "Exchange, Outlook, Teams", True),
    ("Database Team", "DATABASE", "Database administration", True),
    ("Hardware Support", "HARDWARE", "Laptops, peripherals and repairs", True),
    ("Security Team", "SECURITY", "Security operations and incident response", True),
    ("Server Operations", "SERVER_OPS", "Servers, hosting and application platforms", True),
    ("Software Support", "SOFTWARE", "Application support and licensing", True),
    ("Print Services", "PRINT", "Printers and scanning", True),
    ("Finance", "BU_FINANCE", "Business unit", False),
    ("Engineering", "BU_ENGINEERING", "Business unit", False),
    ("Product Design", "BU_DESIGN", "Business unit", False),
    ("Sales", "BU_SALES", "Business unit", False),
    ("Human Resources", "BU_HR", "Business unit", False),
]

CATEGORY_DEPARTMENT = {
    "VPN": "NETWORK", "Network": "NETWORK", "Password": "IAM", "Email": "EMAIL", "Database": "DATABASE",
    "Hardware": "HARDWARE", "Security": "SECURITY", "Server": "SERVER_OPS", "Software": "SOFTWARE", "Printer": "PRINT",
}
CATEGORY_DESCRIPTIONS = {
    "VPN": "Remote access / VPN connectivity", "Network": "Wi-Fi, wired and internet connectivity",
    "Password": "Passwords, lockouts and MFA", "Email": "Email, Outlook, calendar and Teams",
    "Database": "Database access and performance", "Hardware": "Laptops, monitors and peripherals",
    "Security": "Phishing, malware and suspicious activity", "Server": "Server and hosted service outages",
    "Software": "Installation, licensing and application errors", "Printer": "Printing and scanning",
}

# username, full name, role, department code, job title, location, password
USERS = [
    ("admin", "Morgan Admin", "admin", "SERVICE_DESK", "IT Operations Manager", "HQ", "Admin@123"),
    ("itsupport", "Alex Kumar", "it_support", "NETWORK", "Network Engineer", "HQ", "Support@123"),
    ("iam.agent", "Riley Stone", "it_support", "IAM", "Identity Engineer", "HQ", "Support@123"),
    ("mail.agent", "Jordan Blake", "it_support", "EMAIL", "Messaging Engineer", "HQ", "Support@123"),
    ("hw.agent", "Casey Lin", "it_support", "HARDWARE", "Hardware Technician", "HQ", "Support@123"),
    ("sec.agent", "Taylor Reyes", "it_support", "SECURITY", "Security Analyst", "HQ", "Support@123"),
    ("dba.agent", "Sam Okoro", "it_support", "DATABASE", "Database Administrator", "HQ", "Support@123"),
    ("ops.agent", "Drew Park", "it_support", "SERVER_OPS", "Site Reliability Engineer", "HQ", "Support@123"),
    ("app.agent", "Quinn Ellis", "it_support", "SOFTWARE", "Application Support Analyst", "HQ", "Support@123"),
    ("print.agent", "Robin Hale", "it_support", "PRINT", "Print Services Technician", "HQ", "Support@123"),
    ("desk.agent", "Jamie Fox", "it_support", "SERVICE_DESK", "Service Desk Analyst", "HQ", "Support@123"),
    ("johndoe", "John Doe", "employee", "BU_ENGINEERING", "Software Engineer", "NYC Campus", "Employee@123"),
    ("arivera", "Alex Rivera", "employee", "BU_DESIGN", "Staff Product Designer", "NYC Campus", "Employee@123"),
    ("schen", "Sarah Chen", "employee", "BU_ENGINEERING", "Backend Engineer", "Core Infra", "Employee@123"),
    ("dmiller", "David Miller", "employee", "BU_FINANCE", "Payroll Specialist", "Payroll Ops", "Employee@123"),
    ("pnair", "Priya Nair", "employee", "BU_SALES", "Account Executive", "Remote", "Employee@123"),
    ("jokafor", "Joy Okafor", "employee", "BU_HR", "HR Partner", "HQ", "Employee@123"),
    ("lgarcia", "Luis Garcia", "employee", "BU_DESIGN", "UX Researcher", "NYC Campus", "Employee@123"),
    ("tbrooks", "Tessa Brooks", "employee", "BU_FINANCE", "Financial Analyst", "HQ", "Employee@123"),
    ("mkim", "Min Kim", "employee", "BU_ENGINEERING", "Data Engineer", "Remote", "Employee@123"),
    ("rpatel", "Ravi Patel", "employee", "BU_SALES", "Sales Engineer", "HQ", "Employee@123"),
    ("hsingh", "Harper Singh", "employee", "BU_HR", "Recruiter", "HQ", "Employee@123"),
    ("ewhite", "Elena White", "employee", "BU_FINANCE", "Accountant", "HQ", "Employee@123"),
    ("fzhang", "Felix Zhang", "employee", "BU_FINANCE", "Controller", "HQ", "Employee@123"),
    ("gadams", "Grace Adams", "employee", "BU_FINANCE", "Accounts Payable Lead", "HQ", "Employee@123"),
    ("kwright", "Kai Wright", "employee", "BU_ENGINEERING", "QA Engineer", "Remote", "Employee@123"),
    ("bcooper", "Blair Cooper", "employee", "BU_SALES", "Sales Manager", "HQ", "Employee@123"),
]


def parse_front_matter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
    if not m:
        return {}, text
    meta = dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)
    return {k.strip(): v.strip() for k, v in meta.items()}, m.group(2).strip()


async def seed_reference(db, demo_users: bool = True) -> dict:
    roles = {}
    for name, (desc, perms) in ROLES.items():
        role = (await db.execute(select(Role).where(Role.name == name))).scalar_one_or_none()
        if role is None:
            role = Role(name=name, description=desc, permissions=perms)
            db.add(role)
        roles[name] = role
    depts = {}
    for name, code, desc, support in DEPARTMENTS:
        d = (await db.execute(select(Department).where(Department.code == code))).scalar_one_or_none()
        if d is None:
            d = Department(name=name, code=code, description=desc, is_support_team=support,
                           escalation_email=f"{code.lower()}@example.com" if support else None)
            db.add(d)
        depts[code] = d
    await db.flush()
    for cat, dept_code in CATEGORY_DEPARTMENT.items():
        c = (await db.execute(select(TicketCategory).where(TicketCategory.name == cat))).unique().scalar_one_or_none()
        if c is None:
            db.add(TicketCategory(name=cat, description=CATEGORY_DESCRIPTIONS[cat], department_id=depts[dept_code].id,
                                  keywords=DEFAULT_KEYWORDS[cat]))
    users = {}
    for username, full, role, dept, title, loc, pw in (USERS if demo_users else []):
        u = (await db.execute(select(User).where(User.username == username))).unique().scalar_one_or_none()
        if u is None:
            u = User(username=username, email=f"{username}@example.com", full_name=full, role=roles[role],
                     department=depts[dept], job_title=title, location=loc, password_hash=hash_password(pw))
            db.add(u)
        users[username] = u
    await db.flush()
    cats = {c.name: c for c in (await db.execute(select(TicketCategory))).unique().scalars()}
    return {"users": users, "categories": cats, "departments": depts}


async def seed_knowledge(db, cats: dict, admin: User | None) -> int:
    if (await db.execute(select(func.count(KnowledgeDocument.id)))).scalar():
        return 0
    n = 0
    for path in sorted((DATA / "knowledge").glob("*.md")):
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        cat = cats.get(meta.get("category", ""))
        await knowledge.create_document(db, title=meta.get("title", path.stem), content=body,
                                        category_id=cat.id if cat else None, doc_type=meta.get("doc_type", "runbook"),
                                        created_by=admin.id if admin else None, index=False)
        n += 1
    return n


async def seed_history(db, ref: dict) -> int:
    if (await db.execute(select(func.count(Ticket.id)))).scalar():
        return 0
    spec = json.loads((DATA / "seed" / "historical_tickets.json").read_text(encoding="utf-8"))["tickets"]
    users, cats = ref["users"], ref["categories"]
    group_solution: dict = {}
    staff_by_dept = {u.department_id: u for u in users.values() if u.role_name == "it_support"}
    now = utcnow()
    for row in sorted(spec, key=lambda r: -r["days_ago"]):
        cat = cats[row["category"]]
        user = users[row["user"]]
        text = f"{row['title']}. {row['description']}"
        created = now - timedelta(days=row["days_ago"], hours=3)
        ticket = await ticket_svc.create_ticket(
            db, user=user, title=row["title"], description=row["description"], category_id=cat.id,
            intent=detect_intent(text, cat.name), sub_category=None, entities=extract_entities(text),
            ai_confidence=0.9, classification_method="rules", system_priority=row["priority"],
            priority_confidence=0.9, priority_reason="historical import", status=TicketStatus.NEW,
            source="historical_import")
        ticket.sub_category = next((i[2] for i in INTENTS if i[0] == ticket.intent), None)
        ticket.created_at = created
        res = row.get("resolution")
        if res is None:
            ticket.status = row.get("status", TicketStatus.ESCALATED)
            ticket.department_id = cat.department_id
            db.add(TicketEscalation(ticket_id=ticket.id, department_id=cat.department_id, reason="Historical escalation",
                                    package={"ticket_id": ticket.ticket_number, "summary": ticket.title}))
            continue
        ticket.status = TicketStatus.RESOLVED
        ticket.resolved_at = created + timedelta(hours=row["hours_to_resolve"])
        agent_user = staff_by_dept.get(cat.department_id)
        if res.get("reuse_of"):
            sol = group_solution[res["reuse_of"]]
            sol.times_used += 1
            sol.times_successful += 1
            ticket.resolved_by_ai = True
            ticket.resolution_summary = f"Resolved with {sol.title} (reused knowledge SOL-{sol.id})"
            continue
        ticket.assigned_to = agent_user.id if agent_user else None
        ticket.department_id = cat.department_id
        ticket.resolved_by_ai = res["source"] == "agent"
        ticket.resolution_summary = res["summary"]
        sol = await knowledge.create_solution(
            db, title=ticket.title, problem=ticket.description, solution=res["summary"],
            steps=res.get("steps") or knowledge.steps_from_text(res["summary"]), category_id=cat.id,
            intent=ticket.intent, confidence_level=res["level"], source=res["source"], ticket_id=ticket.id,
            root_cause=res.get("root_cause"), automated_actions=res.get("automated_actions", []),
            created_by=agent_user.id if agent_user else None,
            verified_by=agent_user.id if agent_user and res["level"] in ("human_verified", "admin_verified") else None,
            index=False)
        sol.created_at = ticket.resolved_at or created
        sol.times_used, sol.times_successful = 1, 1
        group_solution[row.get("group", ticket.ticket_number)] = sol
    return len(spec)


async def simulate_live_reports() -> list[str]:
    """Replay employee reports through the real chat + agent pipeline, one request per message."""
    from app.services import chat as chat_svc
    from app.tools.executor import decide
    from app.models import AgentAction

    spec = json.loads((DATA / "seed" / "live_reports.json").read_text(encoding="utf-8"))["reports"]
    log = []
    for rep in spec:
        async with async_session_factory() as db:
            user = (await db.execute(select(User).where(User.username == rep["user"]))).unique().scalar_one()
            await chat_svc.new_conversation(db, user)
            reply = await chat_svc.handle_message(db, user, rep["message"], user_priority=rep.get("user_priority"),
                                                  client_env={"platform": "Win32", "language": "en-US"})
            answers = list(rep.get("answers", []))
            guard = 0
            while reply.stage == "clarifying" and guard < 4:
                guard += 1
                answer = answers.pop(0) if answers else (reply.quick_replies[0] if reply.quick_replies else "Just me")
                reply = await chat_svc.handle_message(db, user, answer)
            await db.commit()
            if rep.get("approve") and reply.ticket_id:
                for a in (await db.execute(select(AgentAction).where(AgentAction.ticket_id == reply.ticket_id,
                                                                     AgentAction.status == "pending_approval"))).unique().scalars():
                    await decide(db, a, user, True)
                await db.commit()
            for fb in rep.get("feedback", []):
                if reply.stage != "agent" or not reply.quick_replies:
                    break
                reply = await chat_svc.handle_message(db, user, fb)
                await db.commit()
            ticket = await db.get(Ticket, reply.ticket_id) if reply.ticket_id else None
            log.append(f"  {rep['user']:<9} -> {ticket.ticket_number if ticket else '-':<10} "
                       f"{ticket.status if ticket else reply.stage:<16} {rep['message'][:60]}")
    return log


async def main(simulate: bool) -> None:
    setup_logging()
    settings = get_settings()
    async with async_session_factory() as db:
        ref = await seed_reference(db)
        await db.commit()
        docs = await seed_knowledge(db, ref["categories"], ref["users"]["admin"])
        hist = await seed_history(db, ref)
        await db.commit()
        report = await get_index_manager().rebuild_all(db)
    print(f"Reference data ready. Knowledge docs added: {docs}. Historical tickets added: {hist}.")
    print(f"FAISS indexes rebuilt from the database: {report}")

    if simulate and hist:
        settings.AGENT_TOOLS_ENABLED = False  # deterministic, offline-friendly seeding
        print("Replaying live reports through the chat + agent pipeline:")
        for line in await simulate_live_reports():
            print(line)

    print("\nDemo accounts (change these passwords outside local development):")
    print("  admin      / Admin@123     (administrator)")
    print("  itsupport  / Support@123   (IT support - Network Team; other teams: iam.agent, mail.agent, ...)")
    print("  johndoe    / Employee@123  (employee; also arivera, schen, ewhite, ...)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-simulate", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(simulate=not args.no_simulate))
