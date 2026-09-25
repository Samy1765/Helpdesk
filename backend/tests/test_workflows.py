"""End-to-end API workflows: chatbot -> ticket -> agent -> resolve / retry / escalate, duplicates,
incident correlation, approvals, IT support actions, knowledge loop, analytics."""

from sqlalchemy import func, select

from app.models import AgentRun, LLMUsageLog, TicketSolution
from tests.conftest import chat_until_ticket, login, new_employee

API = "/api/v1"


async def test_greeting_does_not_create_ticket(client):
    h, _ = await new_employee(client)
    r = await client.post(f"{API}/chat/message", headers=h, json={"message": "hello"})
    assert r.status_code == 200 and r.json()["ticket_id"] is None and r.json()["stage"] == "intake"


async def test_chatbot_asks_follow_up_then_generates_structured_ticket(client):
    h, _ = await new_employee(client)
    await client.post(f"{API}/chat/new", headers=h)
    r = (await client.post(f"{API}/chat/message", headers=h, json={"message": "My VPN isn't working."})).json()
    assert r["stage"] == "clarifying" and r["quick_replies"]
    assert "connect" in r["message"].lower()
    reply = await chat_until_ticket(client, h, "My VPN isn't working.", ["Connects then drops out", "Just me"])
    detail = (await client.get(f"{API}/tickets/{reply['ticket_id']}", headers=h)).json()
    t = detail["ticket"]
    assert t["ticket_number"].startswith("INC-") and t["category"] == "VPN" and t["source"] == "ai_chatbot"
    assert t["intent"] and t["priority"] in ("low", "medium", "high", "critical") and t["ai_confidence"] > 0
    assert [s["key"] for s in detail["agent"]["progress"]][:3] == ["understand", "classify", "priority"]


async def test_verified_solution_reused_without_llm_then_resolved(client, db):
    h, user = await new_employee(client)
    reply = await chat_until_ticket(client, h, "VPN keeps timing out on login right after I enter the 2FA code",
                                    ["Just me"])
    sol = reply["payload"]["solution"]
    assert sol["kind"] == "solution" and sol["routing_level"] == "L3_verified_retrieval"
    assert sol["label"] in ("HUMAN-APPROVED SOLUTION", "VERIFIED SOLUTION")
    assert any(a["type"] == "success" for a in reply["payload"]["alerts"])
    # restricted automated actions are proposed, pending approval - never executed automatically
    assert reply["payload"]["approvals"] and all(a["status"] == "pending_approval" for a in reply["payload"]["approvals"])
    before = (await db.execute(select(TicketSolution.times_successful).where(TicketSolution.id == sol["solution_id"]))).scalar()
    r = (await client.post(f"{API}/chat/message", headers=h, json={"message": "Yes, it's fixed"})).json()
    assert r["payload"]["agent"]["state"] == "resolved"
    t = (await client.get(f"{API}/tickets/{reply['ticket_id']}", headers=h)).json()["ticket"]
    assert t["status"] == "resolved" and t["resolved_by_ai"]
    run = (await db.execute(select(AgentRun).where(AgentRun.ticket_id == reply["ticket_id"]))).scalar_one()
    assert run.llm_calls == 0 and run.resolution_status == "resolved"
    after = (await db.execute(select(TicketSolution.times_successful).where(TicketSolution.id == sol["solution_id"]))).scalar()
    assert after == before + 1


async def test_retry_then_escalation_to_correct_department(client):
    h, _ = await new_employee(client)
    reply = await chat_until_ticket(client, h, "Office Wi-Fi is connected but there is no internet on my laptop",
                                    ["Wi-Fi only", "Just me"])
    assert reply["payload"].get("solution")
    r = (await client.post(f"{API}/chat/message", headers=h, json={"message": "No, still not working"})).json()
    if r["payload"]["agent"]["state"] == "verify":  # a second candidate was offered
        assert "different approach" in r["message"]
        r = (await client.post(f"{API}/chat/message", headers=h, json={"message": "No, still not working"})).json()
    assert r["payload"]["agent"]["state"] == "escalated"
    assert r["payload"]["escalation"]["department"] == "Network Team"
    detail = (await client.get(f"{API}/tickets/{reply['ticket_id']}", headers=h)).json()
    assert detail["escalation"]["department"] == "Network Team"
    assert detail["escalation"]["package"] is None  # employees do not see the internal package
    support = await login(client, "itsupport", "Support@123")
    pkg = (await client.get(f"{API}/tickets/{reply['ticket_id']}", headers=support)).json()["escalation"]["package"]
    for key in ("ticket_id", "summary", "category", "priority", "troubleshooting_attempted", "retrieved_solutions",
                "agent_reasoning_summary", "user_information", "recommended_department"):
        assert key in pkg
    assert pkg["troubleshooting_attempted"]


async def test_same_user_duplicate_is_detected(client):
    h, _ = await new_employee(client)
    first = await chat_until_ticket(client, h, "Documents I send to the printer are stuck in the print queue and never print",
                                    ["Jobs stuck in the queue", "Just me"])
    second = await chat_until_ticket(client, h, "My print jobs are stuck in the printer queue, nothing prints",
                                     ["Jobs stuck in the queue", "Just me"])
    assert second["payload"]["agent"]["state"] == "duplicate"
    assert second["payload"]["duplicate"]["number"] == first["ticket_number"]
    t = (await client.get(f"{API}/tickets/{second['ticket_id']}", headers=h)).json()
    assert t["ticket"]["status"] == "duplicate" and t["duplicate_of"]["id"] == first["ticket_id"]


async def test_incident_correlation_groups_reports_from_different_users(client):
    msgs = ["The SharePoint intranet server is down, getting HTTP 503 on every page",
            "Intranet SharePoint site returns 503 service unavailable for me",
            "SharePoint intranet is not responding, 503 error since a few minutes"]
    replies = []
    for m in msgs:
        h, _ = await new_employee(client, "inc")
        replies.append(await chat_until_ticket(client, h, m, ["HTTP 500 / 503 errors", "Just me"]))
    last = replies[-1]["payload"]
    assert last["agent"]["state"] == "linked_incident"
    number = last["incident"]["number"]
    assert number.startswith("INCIDENT-SERVER-")
    support = await login(client, "ops.agent", "Support@123")
    incidents = (await client.get(f"{API}/incidents", headers=support)).json()
    inc = next(i for i in incidents if i["incident_number"] == number)
    assert inc["ticket_count"] >= 2 and inc["priority"] in ("high", "critical")
    # resolving the incident fans out to linked tickets and creates verified knowledge
    r = await client.post(f"{API}/incidents/{inc['id']}/resolve", headers=support,
                          json={"resolution": "Recycled the SharePoint application pool on WEB-02.", "root_cause": "App pool crash"})
    assert r.status_code == 200 and r.json()["tickets_resolved"] >= 1


async def test_security_issue_is_escalated_by_policy(client):
    h, _ = await new_employee(client)
    reply = await chat_until_ticket(client, h, "I clicked the link in a fake email and entered my password",
                                    ["I clicked a link / entered my password", "Just me"])
    p = reply["payload"]
    assert p["ticket"]["category"] == "Security"
    assert p["agent"]["state"] == "escalated" and p["escalation"]["department"] == "Security Team"
    assert p["agent"]["routing_level"] == "L0_policy"


async def test_priority_alert_when_user_inflates(client):
    h, _ = await new_employee(client)
    reply = await chat_until_ticket(client, h, "I would like to change my desktop wallpaper theme, not urgent",
                                    ["Just me"], user_priority="critical")
    assert reply["payload"]["priority_assessment"]["system_priority"] == "low"
    assert any("appears higher" in a["message"] for a in reply["payload"]["alerts"])
    t = (await client.get(f"{API}/tickets/{reply['ticket_id']}", headers=h)).json()["ticket"]
    assert t["user_priority"] == "critical" and t["system_priority"] == "low"


async def test_approval_permissions(client):
    h, _ = await new_employee(client)
    reply = await chat_until_ticket(client, h, "My account is locked out after I changed my password", ["Just me"])
    approvals = reply["payload"]["approvals"]
    assert approvals and approvals[0]["permission"] == "restricted"
    other, _ = await new_employee(client)
    assert (await client.post(f"{API}/actions/{approvals[0]['id']}/decision", headers=other,
                              json={"approve": True})).status_code == 404
    r = await client.post(f"{API}/actions/{approvals[0]['id']}/decision", headers=h, json={"approve": True})
    assert r.status_code == 200 and r.json()["action"]["status"] == "approved"
    assert r.json()["action"]["result"]["mode"] == "dry_run"
    again = await client.post(f"{API}/actions/{approvals[0]['id']}/decision", headers=h, json={"approve": True})
    assert again.status_code == 409


async def test_employee_cannot_see_other_tickets(client):
    h1, _ = await new_employee(client)
    h2, _ = await new_employee(client)
    reply = await chat_until_ticket(client, h1, "Excel crashes when I open big spreadsheets", ["It crashes or freezes", "Just me"])
    assert (await client.get(f"{API}/tickets/{reply['ticket_id']}", headers=h2)).status_code == 404
    listing = (await client.get(f"{API}/tickets", headers=h2)).json()
    assert all(t["id"] != reply["ticket_id"] for t in listing["items"])


async def test_it_support_resolution_becomes_reusable_knowledge(client, db):
    h, _ = await new_employee(client)
    reply = await chat_until_ticket(client, h, "The Zephyr timesheet app shows error ZX-771 when I submit hours",
                                    ["It crashes or freezes", "Just me"])
    support = await login(client, "app.agent", "Support@123")
    tid = reply["ticket_id"]
    assert (await client.post(f"{API}/support/tickets/{tid}/accept", headers=support)).status_code == 200
    r = await client.post(f"{API}/support/tickets/{tid}/resolve", headers=support, json={
        "resolution": "Clear the Zephyr timesheet cache from the profile menu and sign in again; ZX-771 is a stale session.",
        "root_cause": "Stale session token", "steps": ["Open profile menu", "Clear cache", "Sign in again"],
        "save_as_knowledge": True})
    assert r.status_code == 200 and r.json()["solution"]["confidence_level"] == "human_verified"
    # a future, similar report now retrieves the verified human solution without an LLM call
    h2, _ = await new_employee(client)
    nxt = await chat_until_ticket(client, h2, "Zephyr timesheet gives error ZX-771 when submitting my hours",
                                  ["It crashes or freezes", "Just me"])
    sol = nxt["payload"]["solution"]
    assert sol["solution_id"] == r.json()["solution"]["id"] and sol["label"] == "HUMAN-APPROVED SOLUTION"


async def test_support_can_correct_classification(client):
    h, _ = await new_employee(client)
    reply = await chat_until_ticket(client, h, "My monitor flickers with lines on the display", ["Screen / display problem", "Just me"])
    support = await login(client, "hw.agent", "Support@123")
    cats = (await client.get(f"{API}/meta/categories", headers=support)).json()
    software = next(c for c in cats if c["name"] == "Software")
    r = await client.patch(f"{API}/support/tickets/{reply['ticket_id']}/classification", headers=support,
                           json={"category_id": software["id"], "priority": "high", "reason": "driver issue"})
    assert r.status_code == 200 and r.json()["category"] == "Software" and r.json()["priority"] == "high"
    detail = (await client.get(f"{API}/tickets/{reply['ticket_id']}", headers=support)).json()
    assert {"category_corrected", "priority_corrected"} <= {e["type"] for e in detail["events"]}


async def test_admin_analytics_are_computed_from_data(client, db):
    admin = await login(client, "admin", "Admin@123")
    data = (await client.get(f"{API}/admin/analytics?days=30", headers=admin)).json()
    total = (await db.execute(select(func.count()).select_from(AgentRun))).scalar()
    assert data["overview"]["total_tickets"] > 0
    assert sum(d["tickets"] for d in data["tickets_per_day"]) == data["overview"]["tickets_in_window"]
    assert sum(r["count"] for r in data["routing_levels"]) == total
    assert data["llm_usage"]["calls"] == (await db.execute(select(func.count()).select_from(LLMUsageLog))).scalar()
    assert data["savings"]["runs_without_llm"] >= 1
    system = (await client.get(f"{API}/admin/system", headers=admin)).json()
    assert system["vector_store"]["indexes"]["knowledge"] > 0


async def test_manual_ticket_and_feedback_endpoint(client):
    h, _ = await new_employee(client)
    r = await client.post(f"{API}/tickets", headers=h, json={
        "title": "Printer paper jam", "description": "The printer near reception shows a paper jam error"})
    assert r.status_code == 201
    tid = r.json()["ticket"]["id"]
    if r.json()["agent"]["state"] == "verify":
        fb = await client.post(f"{API}/tickets/{tid}/feedback", headers=h, json={"resolved": True})
        assert fb.status_code == 200 and fb.json()["ticket"]["status"] == "resolved"
        assert (await client.post(f"{API}/tickets/{tid}/feedback", headers=h, json={"resolved": True})).status_code == 409


async def test_ticket_attachment_access_control_and_dashboard(client):
    h, _ = await new_employee(client)
    reply = await chat_until_ticket(client, h, "Outlook crashes every time I open it", ["Outlook crashes or won't open", "Just me"])
    tid = reply["ticket_id"]
    files = {"file": ("error.txt", b"Faulting module: OUTLOOK.EXE", "text/plain")}
    r = await client.post(f"{API}/attachments", headers=h, files=files, data={"ticket_id": str(tid)})
    assert r.status_code == 201
    token = r.json()["token"]
    assert (await client.get(f"{API}/attachments/{token}", headers=h)).status_code == 200
    other, _ = await new_employee(client)
    assert (await client.get(f"{API}/attachments/{token}", headers=other)).status_code == 404
    assert (await client.post(f"{API}/attachments", headers=other, files=files, data={"ticket_id": str(tid)})).status_code == 404
    bad = {"file": ("run.exe", b"MZ", "application/x-msdownload")}
    assert (await client.post(f"{API}/attachments", headers=h, files=bad)).status_code == 415
    detail = (await client.get(f"{API}/tickets/{tid}", headers=h)).json()
    assert detail["attachments"][0]["filename"] == "error.txt"
    dash = (await client.get(f"{API}/dashboard", headers=h)).json()
    recent = next(t for t in dash["recent_tickets"] if t["id"] == tid)
    assert 0 < recent["pipeline_progress"] <= 100


async def test_health_and_knowledge_search(client):
    assert (await client.get("/health")).json()["status"] == "healthy"
    h, _ = await new_employee(client)
    r = (await client.get(f"{API}/knowledge/search", headers=h, params={"q": "outlook keeps crashing"})).json()
    assert r["documents"] and r["documents"][0]["category"] == "Email"
